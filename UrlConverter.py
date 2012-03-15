from optparse import OptionParser


class UrlConverter(object):

    def __init__(self, base_file_name, max_count):
        self.fileToChange = open(base_file_name, 'r')
        self.max_count = max_count

    def mutate(self):
        count = 0
        fp = open("urls.txt", "w")
        urls = self.fileToChange.read().split()
        for url in urls:
            if not url.startswith('http://'):
                url = 'http://%s' % url

            fp.write(url + '\n')
            count += 1
            print count
            if count == self.max_count:
                fp.close()
                break

        fp.close()
        self.fileToChange.close()

if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option('-s', '--seed-file', dest="seed_file", default="urls.txt")
    parser.add_option('-m', '--max-count', dest="max_count", default=100)
    options, args = parser.parse_args()

    converter = UrlConverter(options.seed_file, int(options.max_count))
    converter.mutate()
