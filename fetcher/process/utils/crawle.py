"""CRAWL-E is a highly distributed web crawling framework."""
from datetime import datetime
import Queue, cStringIO, gzip, httplib, logging, mimetypes, resource, socket
import sys, subprocess, threading, time, urllib, urlparse, pickle
from optparse import OptionParser

import pika
from pika.adapters import BlockingConnection

VERSION = '0.6.4'
HEADER_DEFAULTS = {'Accept':'*/*', 'Accept-Language':'en-us,en;q=0.8',
                   'User-Agent':'CRAWL-E/%s' % VERSION}
DEFAULT_SOCKET_TIMEOUT = 10
STOP_CRAWLE = False

class CrawleException(Exception):
    """Base Crawle exception class."""
class CrawleRequestAborted(CrawleException):
    """Exception raised when the handler pre_process function sets the
    response_url to None to indicate not to visit the URL."""
class CrawleStopped(CrawleException):
    """Exception raised when the crawler is stopped."""
class CrawleUnsupportedScheme(CrawleException):
    """Exception raised when the url does not start with "http" or "https"."""
class CrawleRedirectsExceeded(CrawleException):
    """Exception raised when the number of redirects exceeds the limit."""

class Handler(object):
    """An _abstract_ class for handling what urls to retrieve and how to
    parse and save them. The functions of this class need to be designed in
    such a way so that they are threadsafe as multiple threads will have
    access to the same instance.
    """

    def pre_process(self, request_response):
        """pre_process is called directly before making the reqeust. Any of the
        request parameters can be modified here.

e       Setting the responseURL to None will cause the request to be dropped.
        This is useful for testing if a redirect link should be followed.
        """
        return

    def process(self, request_response, queue):
        """Process is called after the request has been made. It needs to be
        implemented by a subclass.

        Keyword Arguments:
        request_response -- the request response object
        queue -- the handler to the queue class
        """
        assert request_response and queue # pychecker hack
        raise NotImplementedError(' '.join(('Handler.process must be defined',
                                            'in a subclass')))

class RequestResponse(object):
    """This class is a container for information pertaining to requests and
    responses."""

    def __init__(self, url, headers=None, method='GET', params=None,
                 files=None, redirects=10):
        """Constructs a RequestResponse object.

        Keyword Arguments:
        url -- The url to request.
        headers -- The http request headers.
        method -- The http request method.
        params -- The http parameters as a dictionary.
        files -- A list of tuples containing key, filename, filedata
        redirects -- The maximum number of redirects to follow.
        """
        self.error = None
        self.redirects = redirects
        self.retries = 0
        self.frame_depth = 0
        self.name = urlparse.urlparse(url).netloc
        self.last_attempt = True

        self.request_headers = headers
        self.request_url = url
        self.request_method = method
        self.request_params = params
        self.request_files = files

        self.response_status = None
        self.response_url = url
        self.response_headers = None
        self.response_body = None
        self.response_time = None


class HTTPConnectionQueue(object):
    """This class handles the queue of sockets for a particular address.

    This essentially is a queue of socket objects which also adds a transparent
    field to each connection object which is the request_count. When the
    request_count exceeds the REQUEST_LIMIT the connection is automatically
    reset.
    """
    REQUEST_LIMIT = None

    @staticmethod
    def connection_object(address, encrypted):
        """Very simply return a HTTP(S)Connection object."""
        if encrypted:
            connection = httplib.HTTPSConnection(*address)
        else:
            connection = httplib.HTTPConnection(*address)
        connection.request_count = 0
        return connection

    def __init__(self, address, encrypted=False, max_conn=None):
        """Constructs a HTTPConnectionQueue object.

        Keyword Arguments:
        address -- The address for which this object maps to.
        encrypted -- Where or not the connection is encrypted.
        max_conn -- The maximum number of connections to maintain
        """
        self.address = address
        self.encrypted = encrypted
        self.queue = Queue.Queue(0)
        self.connections = 0
        self.max_conn = max_conn

    def destroy(self):
        """Destroy the HTTPConnectionQueue object."""
        try:
            while True:
                connection = self.queue.get(block=False)
                connection.close()
        except Queue.Empty: pass

    def get(self):
        """Return a HTTP(S)Connection object for the appropriate address.

        First try to return the object from the queue, however if the queue
        is empty create a new socket object to return.

        Dynamically add new field to HTTPConnection called request_count to
        keep track of the number of requests made with the specific connection.
        """
        try:
            connection = self.queue.get(block=False)
            self.connections -= 1
            # Reset the connection if exceeds request limit
            if (self.REQUEST_LIMIT and
                connection.request_count >= self.REQUEST_LIMIT):
                connection.close()
                connection = HTTPConnectionQueue.connection_object(
                    self.address, self.encrypted)
        except Queue.Empty:
            connection = HTTPConnectionQueue.connection_object(self.address,
                                                               self.encrypted)
        return connection

    def put(self, connection):
        """Put the HTTPConnection object back on the queue."""
        connection.request_count += 1
        if self.max_conn != None and self.connections + 1 > self.max_conn:
            connection.close()
        else:
            self.queue.put(connection)
            self.connections += 1


class QueueNode(object):
    """This class handles an individual node in the CQueueLRU."""

    def __init__(self, connection_queue, key, next=None):
        """Construct a QueueNode object.

        Keyword Arguments:
        connection_queue -- The ConnectionQueue object.
        key -- The unique identifier that allows one to perform a reverse
               lookup in the hash table.
        next -- The previous least recently used item.
        """

        self.connection_queue = connection_queue
        self.key = key
        self.next = next
        if next:
            self.next.prev = self
        self.prev = None

    def remove(self):
        """Properly remove the node"""
        if self.prev:
            self.prev.next = None
        self.connection_queue.destroy()

class CQueueLRU(object):
    """This class manages a least recently used list with dictionary lookup."""

    def __init__(self, max_queues=None, max_conn=None):
        """Construct a CQueueLRU object.

        Keyword Arguments:
        max_queues -- The maximum number of unique queues to manage. When only
                      crawling a single domain, one should be sufficient.
        max_conn -- The maximum number of connections that may persist within
                    a single ConnectionQueue.
        """

        self.lock = threading.Lock()
        self.max_queues = max_queues
        self.max_conn = max_conn
        self.table = {}
        self.newest = None
        self.oldest = None

    def __getitem__(self, key):
        """Return either a HTTP(S)Connection object.

        Fetches an already utilized object if one exists.
        """
        self.lock.acquire()
        if key in self.table:
            connection = self.table[key].connection_queue.get()
        else:
            connection = HTTPConnectionQueue.connection_object(*key)
        self.lock.release()
        return connection

    def __setitem__(self, key, connection):
        """Store the HTTP(S)Connection object.

        This function ensures that there are at most max_queues. In the event
        there are too many, the oldest inactive queues will be deleted.
        """
        self.lock.acquire()
        if key in self.table:
            node = self.table[key]
            # move the node to the head of the list
            if self.newest != node:
                node.prev.next = node.next
                if self.oldest != node:
                    node.next.prev = node.prev
                else:
                    self.oldest = node.prev
                node.prev = None
                node.next = self.newest
                self.newest = node.next.prev = node
        else:
            # delete the oldest while too many
            while (self.max_queues != None and
                   len(self.table) + 1 > self.max_queues):
                if self.oldest == self.newest:
                    self.newest = None
                del self.table[self.oldest.key]
                prev = self.oldest.prev
                self.oldest.remove()
                self.oldest = prev
            connection_queue = HTTPConnectionQueue(*key,
                                                    max_conn=self.max_conn)
            node = QueueNode(connection_queue, key, self.newest)
            self.newest = node
            if not self.oldest:
                self.oldest = node
            self.table[key] = node
        node.connection_queue.put(connection)
        self.lock.release()


class HTTPConnectionControl(object):
    """This class handles HTTPConnectionQueues by storing a queue in a
    dictionary with the address as the index to the dictionary. Additionally
    this class handles resetting the connection when it reaches a specified
    request limit.
    """

    def __init__(self, handler, max_queues=None, max_conn=None, timeout=None):
        """Constructs the HTTPConnection Control object. These objects are to
        be shared between each thread.

        Keyword Arguments:
        handler -- The Handler class for checking if a url is valid.
        max_queues -- The maximum number of connection_queues to maintain.
        max_conn -- The maximum number of connections (sockets) allowed for a
                    given connection_queue.
        timeout -- The socket timeout value.
        """
        socket.setdefaulttimeout(timeout)
        self.cq_lru = CQueueLRU(max_queues, max_conn)
        self.handler = handler

    def _build_request(self, req_res):
        """Construct request headers and URI from request_response object."""
        u = urlparse.urlparse(req_res.response_url)
        if u.scheme not in ['http', 'https'] or u.netloc == '':
            raise CrawleUnsupportedScheme()

        address = socket.gethostbyname(u.hostname), u.port
        encrypted = u.scheme == 'https'

        url = urlparse.urlunparse(('', '', u.path, u.params, u.query, ''))
        if req_res.request_headers:
            headers = req_res.request_headers
        else:
            headers = {}
        if 'Accept' not in headers:
            headers['Accept'] = HEADER_DEFAULTS['Accept']
        if 'Accept-Encoding' not in headers:
            headers['Accept-Encoding'] = 'gzip'
        if 'Accept-Languge' not in headers:
            headers['Accept-Language'] = HEADER_DEFAULTS['Accept-Language']
        if 'Host' not in headers:
            if u.port == None:
                headers['Host'] = u.hostname
            else:
                headers['Host'] = '%s:%d' % (u.hostname, u.port)
        if 'User-Agent' not in headers:
            headers['User-Agent'] = HEADER_DEFAULTS['User-Agent']
        return address, encrypted, url, headers

    def request(self, req_res):
        """Handles the request to the server."""
        if STOP_CRAWLE:
            raise CrawleStopped()

        self.handler.pre_process(req_res)
        if req_res.response_url == None:
            raise CrawleRequestAborted()

        address, encrypted, url, headers = self._build_request(req_res)
        connection = self.cq_lru[(address, encrypted)]

        try:
            start = time.time()
            if req_res.request_files:
                content_type, data = self.encode_multipart_formdata(
                    req_res.request_params, req_res.request_files)
                headers['Content-Type'] = content_type
            elif req_res.request_params:
                data = urllib.urlencode(req_res.request_params)
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
            else:
                data = ''
            connection.request(req_res.request_method, url, data, headers)
            response = connection.getresponse()
            response_time = time.time() - start
            response_body = response.read()
            self.cq_lru[(address, encrypted)] = connection
        except Exception:
            connection.close()
            site = urllib.urlopen(req_res.response_url)
            res = site.read()
            response_time = time.time() - start
            response_body = res
            if response_body == None:
                raise


        if response.status in (301, 302, 303) and req_res.redirects != None:
            if req_res.redirects <= 0:
                raise CrawleRedirectsExceeded()
            req_res.redirects -= 1
            redirect_url = response.getheader('location')
            req_res.response_url = urlparse.urljoin(req_res.response_url,
                                                    redirect_url)
            self.request(req_res)
        else:
            req_res.response_time = response_time
            req_res.response_status = response.status
            req_res.response_headers = dict(response.getheaders())
            if ('content-encoding' in req_res.response_headers and
                req_res.response_headers['content-encoding'] == 'gzip'):
                try:
                    fileobj = cStringIO.StringIO(response_body)
                    temp = gzip.GzipFile(fileobj=fileobj)
                    req_res.response_body = temp.read()
                    temp.close()
                    fileobj.close()
                except IOError:
                    # HACK for pages that append plain text to gzip output
                    sb = subprocess.Popen(['zcat'], stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE)
                    sb.stdin.write(response_body)
                    sb.stdin.close()
                    req_res.response_body = sb.stdout.read()
                    del sb
            else:
                req_res.response_body = response_body

    # The following function is modified from the snippet at:
    # http://code.activestate.com/recipes/146306/
    def encode_multipart_formdata(self, fields, files):
        """Encode data properly when files are uploaded.

        Keyword Arguments:
        fields -- A dictionary containing key value pairs for form submission
        files -- A list of tuples with key, filename, file data for form
                 submission.
        """
        default_type = 'application/octet-stream'
        BOUNDARY = '----------ThIs_Is_tHe_bouNdaRY_$'
        CRLF = '\r\n'
        L = []
        for key, value in fields.items():
            L.append('--' + BOUNDARY)
            L.append('Content-Disposition: form-data; name="%s"' % key)
            L.append('')
            L.append(value)
        for (key, filename, value) in files:
            L.append('--' + BOUNDARY)
            L.append('Content-Disposition: form-data; name="%s"; filename="%s"'
                     % (key, filename))
            content_type = mimetypes.guess_type(filename)[0] or default_type
            L.append('Content-Type: %s' % content_type)
            L.append('')
            L.append(value)
        L.append('--' + BOUNDARY + '--')
        L.append('')
        body = CRLF.join(L)
        content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
        return content_type, body


class ControlThread(threading.Thread):
    """A single thread of control"""

    def __init__(self, connection_control, handler, queue):
        """Sets up the ControlThread.

        Keyword Arguments:
        connection_control -- A HTTPConnectionControl object. This object is
                              shared amongst the threads
        handler -- The handler class for parsing the returned information
        queue	-- The handle to the queue class which implements get and put.
        """
        threading.Thread.__init__(self)
        self.connection_control = connection_control
        self.handler = handler
        self.queue = queue

    def run(self):
        """This is the execution order of a single thread.

        The threads will stop when STOP_CRAWLE becomes true, or when the queue
        raises Queue.Empty.
        """
        while not STOP_CRAWLE:
            try:
                request_response = self.queue.get()
            except Queue.Empty:
                break

            try:
                self.connection_control.request(request_response)
            except Exception, e:
                request_response.error = e
            self.handler.process(request_response, self.queue)
            self.queue.work_complete()


class Controller(object):
    """The primary controller manages all the threads."""
	
    def __init__(self, handler, queue, num_threads=1,
                 timeout=DEFAULT_SOCKET_TIMEOUT):
        """Create the controller object

        Keyword Arguments:
        handler -- The Handler class each thread will use for processing
        queue -- The handle the the queue class
        num_threads -- The number of threads to spawn (Default 1)
        timeout -- The socket timeout time
        """
        nofiles = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
        queues = nofiles * 2 / (num_threads * 3)
        self.connection_ctrl = HTTPConnectionControl(handler=handler,
                                                     max_queues=queues,
                                                     max_conn=num_threads,
                                                     timeout=timeout)
        self.handler = handler

        self.threads = []
        for _ in range(num_threads):
            thread = ControlThread(handler=handler, queue=queue,
                                   connection_control=self.connection_ctrl)
            self.threads.append(thread)

    def start(self):
        """Starts all threads"""
        for thread in self.threads:
            thread.start()

    def join(self):
        """Join on all threads"""
        for thread in self.threads:
            while 1:
                thread.join(1)
                if not thread.isAlive():
                    break

    def stop(self):
        """Stops all threads gracefully"""
        global STOP_CRAWLE
        STOP_CRAWLE = True
        self.join()


class VisitURLHandler(Handler):
    """Very simple example handler which simply visits the page.

    This handler just demonstrates how to interact with the queue.
    """

    def process(self, info, queue):
        """Puts item back on the queue if the request was no successful."""
        if info['status'] != 200:
            print 'putting %s back on queue' % info['url']
            queue.put(info['url'])


class CrawlQueue(object):
    """Crawl Queue is a mostly abstract concurrent Queue class.

    Users of this class must implement their specific __init__, _get, and _put
    functions both initialize their queue, get items from the queue, and put
    items into the queue.

    The CrawlQueue class takes care of concurrency issues, so that subclass
    implementations can be assured atomic accesses to the user defined _get and
    _put functions. As such both the user defined _get and _put functions
    should be nonblocking.

    In addition to assuring atomic access, the CrawlQueue class manages the
    number of outstanding workers so that it only raises Queue.Empty when both
    its queue it empty and there is no outstanding work.
    """

    def __init__(self, single_threaded=False):
        """Initializes the CrawlQueue class with a condition variable and
        container for the numer of workers."""
        if not single_threaded:
            self._lock = threading.Lock()
            self.cv = threading.Condition(self._lock)
        else:
            self.cv = None
        self._workers = 0

    def get(self):
        """The interface to obtaining an object from the queue.  This function
        manages the concurrency and waits for more items if there is
        outstanding work, otherwise it raises Queue.Empty. This class should
        not be overwritten, but rather the user should write a _get class.
        """
        while True:
            if self.cv:
                self.cv.acquire()
            try:
                item = self._get()
                self._workers += 1
                return item
            except Queue.Empty:
                if self._workers == 0:
                    if self.cv:
                        self.cv.notify_all()
                    raise
                if not self.cv:
                    raise Exception('Invalid single thread handling')
                self.cv.wait()
            finally:
                if self.cv:
                    self.cv.release()

    def put(self, item):
        """The interface for putting an item on the queue. This function
        manages concurrency and notifies other threads when an item is
        added."""
        if self.cv:
            self.cv.acquire()
        try:
            self._put(item)
            if self.cv:
                self.cv.notify()
        finally:
            if self.cv:
                self.cv.release()

    def work_complete(self):
        """Called by the ControlThread after the user defined handler has
        returned thus indicating no more items will be added to the queue from
        that thread before the next call to get."""
        if self.cv:
            self.cv.acquire()
        if self._workers > 0:
            self._workers -= 1
        if self.cv:
            self.cv.notify()
            self.cv.release()

    def _get(self):
        """Function to be implemented by the user."""
        raise NotImplementedError('CrawlQueue._get() must be implemented')

    def _put(self, item):
        """Function to be implemented by the user."""
        assert item # pychecker hack
        raise NotImplementedError('CrawlQueue._put(...) must be implemented')

class RabbitMQProcessor(CrawlQueue):
    """class created to encapsulate the rabbit reading and rewriting proccess
    to make common interface towards already existing crawle code
    Author: Maximiliano Mendez
    """

    def __init__(self, host, queue_name):
        super(RabbitMQProcessor, self).__init__()
        self.queue_name = queue_name
        self.parameters = pika.ConnectionParameters(host)
        self.connection = BlockingConnection(self.parameters)

        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=self.queue_name, durable=True,
                           exclusive=False, auto_delete=False)

    def _get(self):
        method, header, body = self.channel.basic_get(queue=self.queue_name)

        if method.NAME == 'Basic.GetEmpty':
            raise Queue.Empty
        req_res = pickle.loads(body)
        self.channel.basic_ack(delivery_tag=method.delivery_tag)
        return req_res

    def _put(self, req_res):
        message = pickle.dumps(req_res)
        self.channel.basic_publish(exchange='',
                                   routing_key=self.queue_name,
                                   body=message,
                                   properties=pika.BasicProperties(
                                   content_type="text/plain",
                                   delivery_mode=1))

    def stop(self):
        self.connection.close()

class URLQueue(CrawlQueue):
    """URLQueue is the most basic queue type and is all that is needed for
    most situations. Simply, it queues full urls."""

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(formatter)
    logger = logging.getLogger('queue')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(sh)

    LOG_STRING = 'Crawled: %d Remaining: %d RPS: %.2f (%.2f avg)'

    def __init__(self, seed_file=None, seed_urls=None, single_threaded=False, log_after=1000):
        """Sets up the URLQueue by creating a queue.

        Keyword arguments:
        seedfile -- file containing urls to seed the queue (default None)
        """
        super(URLQueue, self).__init__(single_threaded)
        self.queue = []
        self.start_time = self.block_time = None
        self.total_items = 0
        self.log_after = log_after

        # Add seeded items to the queue
        if seed_file:
            try:
                fp = open(seed_file)
            except IOError:
                raise Exception('Could not open seed file')
            for line in fp:
                self.queue.append(RequestResponse(line.strip()))
            fp.close()
            URLQueue.logger.info('Queued: %d from seed file' % len(self.queue))
        if seed_urls:
            [self.queue.put(RequestResponse(x)) for x in seed_urls]
            URLQueue.logger.info('Queued: %d from seed url' % len(seed_urls))
        if len(self.queue) == 0:
            URLQueue.logger.info('Starting with empty queue')

    def save(self, save_file):
        """Outputs queue to file specified. On error prints queue to screen."""
        try:
            fp = open(save_file, 'w')
        except IOError:
            URLQueue.logger.warn('Could not open file for saving.')
            fp = sys.stdout
        items = 0
        for item in self.queue:
            fp.write('%s\n' % item)
            items += 1
        if fp != sys.stdout:
            fp.close()
        URLQueue.logger.info('Saved %d items.' % items)

    def _get(self):
        """Return url at the head of the queue or raise Queue.Empty"""
        if len(self.queue):
            url = self.queue.pop(0)
            self.total_items += 1
            if self.start_time == None:
                self.start_time = self.block_time = time.time()
            elif (self.log_after and
                  self.total_items % self.log_after == 0):
                now = time.time()
                rps_now = self.log_after / (now - self.block_time)
                rps_avg = self.total_items / (now - self.start_time)
                log = URLQueue.LOG_STRING % (self.total_items,
                                             len(self.queue), rps_now,
                                             rps_avg)
                URLQueue.logger.info(log)
                self.block_time = now
            return url
        else:
            raise Queue.Empty

    def _put(self, url):
        """Puts the item back on the queue."""
        self.queue.insert(0, url)

def quick_request(url, redirects=30, timeout=30):
    """Convenience function to quickly request a URL within CRAWl-E."""
    cc = HTTPConnectionControl(Handler(), timeout=timeout)
    rr = RequestResponse(url, redirects=redirects)
    cc.request(rr)
    return rr

def run_crawle(argv, handler, log_after=1):
    """The typical way to start CRAWL-E"""
    before = datetime.now()

    parser = OptionParser()
    parser.add_option('-t', '--threads', help='number of threads to use',
                      type='int', default=1)
    parser.add_option('-s', '--seed', help='file to seed queue with')
    parser.add_option('-u', '--url', help='url to seed queue with',
                      action='append', metavar='URL', dest='urls')
    parser.add_option('-S', '--save', help='file to save remaining urls to')
    options, args = parser.parse_args()

    #queue_handler = URLQueue(seed_file=options.seed, seed_urls=options.urls)
    queue_handler = RabbitMQProcessor('localhost', 'test_queue')
    controller = Controller(handler=handler, queue=queue_handler,
                            num_threads=options.threads)
    controller.start()
    try:
        controller.join()
    except KeyboardInterrupt:
        controller.stop()
    if options.save:
        queue_handler.save(options.save)

    queue_handler.stop()

    after = datetime.now()

    print after - before

if __name__ == '__main__':
    """Basic example of how to start CRAWL-E."""
    run_crawle(sys.argv, handler=VisitURLHandler())
