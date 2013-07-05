# -*- coding: utf-8 -*-
"""
Unit and integration tests for pylinkchecker
"""
from __future__ import unicode_literals, absolute_import

import os
import sys
import time
import threading
import unittest

import pylinkchecker.compat as compat
from pylinkchecker.compat import SocketServer, SimpleHTTPServer, get_url_open
from pylinkchecker.crawler import (open_url, PageCrawler, WORK_DONE,
        ThreadSiteCrawler)
from pylinkchecker.models import (Config, WorkerInit, WorkerConfig, WorkerInput,
        PARSER_STDLIB)
from pylinkchecker.urlutil import get_clean_url_split, get_absolute_url_split


TEST_FILES_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
        'testfiles')


### UTILITY CLASSES AND FUNCTIONS ###

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass


def start_http_server():
    """Starts a simple http server for the test files"""
    # For the http handler
    os.chdir(TEST_FILES_DIR)
    handler = SimpleHTTPServer.SimpleHTTPRequestHandler
    httpd = ThreadedTCPServer(("localhost", 0), handler)
    ip, port = httpd.server_address

    httpd_thread = threading.Thread(target=httpd.serve_forever)
    httpd_thread.setDaemon(True)
    httpd_thread.start()

    return (ip, port, httpd, httpd_thread)


def has_multiprocessing():
    has_multi = False

    try:
        import multiprocessing
        has_multi = True
    except Exception:
        pass

    return has_multi


def has_gevent():
    has_gevent = False

    try:
        import gevent
        has_gevent = True
    except Exception:
        pass

    return has_gevent


### UNIT AND INTEGRATION TESTS ###


class ConfigTest(unittest.TestCase):

    def setUp(self):
        self.argv = sys.argv

    def tearDown(self):
        sys.argv = self.argv

    def test_accepted_hosts(self):
        sys.argv = ['pylinkchecker', 'http://www.example.com/']
        config = Config()
        config.parse_config()
        self.assertTrue('www.example.com' in config.accepted_hosts)

        sys.argv = ['pylinkchecker', '-H', 'www.example.com',
                'http://example.com', 'foo.com', 'http://www.example.com/',
                'baz.com']
        config = Config()
        config.parse_config()

        self.assertTrue('www.example.com' in config.accepted_hosts)
        self.assertTrue('example.com' in config.accepted_hosts)
        self.assertTrue('foo.com' in config.accepted_hosts)
        self.assertTrue('baz.com' in config.accepted_hosts)


class URLUtilTest(unittest.TestCase):

    def test_clean_url_split(self):
        self.assertEqual("http://www.example.com",
            get_clean_url_split("www.example.com").geturl())
        self.assertEqual("http://www.example.com",
            get_clean_url_split("//www.example.com").geturl())
        self.assertEqual("http://www.example.com",
            get_clean_url_split("http://www.example.com").geturl())

        self.assertEqual("http://www.example.com/",
            get_clean_url_split("www.example.com/").geturl())
        self.assertEqual("http://www.example.com/",
            get_clean_url_split("//www.example.com/").geturl())
        self.assertEqual("http://www.example.com/",
            get_clean_url_split("http://www.example.com/").geturl())

    def test_get_absolute_url(self):
        base_url_split = get_clean_url_split(
                "https://www.example.com/hello/index.html")
        self.assertEqual("https://www.example2.com/test.js",
            get_absolute_url_split("//www.example2.com/test.js",
                    base_url_split).geturl())
        self.assertEqual("https://www.example.com/hello2/test.html",
            get_absolute_url_split("/hello2/test.html",
                    base_url_split).geturl())
        self.assertEqual("https://www.example.com/hello/test.html",
            get_absolute_url_split("test.html", base_url_split).geturl())
        self.assertEqual("https://www.example.com/test.html",
            get_absolute_url_split("../test.html", base_url_split).geturl())



class CrawlerTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        (cls.ip, cls.port, cls.httpd, cls.httpd_thread) = start_http_server()
        # FIXME replace by thread synchronization on start
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def setUp(self):
        # We must do this because Python 2.6 does not have setUpClass
        # This will only be executed if setUpClass is ignored.
        # It will not be shutdown properly though, but this does not prevent
        # the unit test to run properly
        if not hasattr(self, 'port'):
            (self.ip, self.port, self.httpd, self.httpd_thread) =\
                    start_http_server()
            # FIXME replace by thread synchronization on start
            time.sleep(0.2)
        self.argv = sys.argv

    def tearDown(self):
        sys.argv = self.argv

    def get_url(self, test_url):
        return "http://{0}:{1}{2}".format(self.ip, self.port, test_url)

    def get_page_crawler(self, url):
        url = self.get_url(url)
        url_split = get_clean_url_split(url)
        input_queue = compat.Queue.Queue()
        output_queue = compat.Queue.Queue()

        worker_config = WorkerConfig(username=None, password=None, types=['a',
                'img', 'link', 'script'], timeout=5, parser=PARSER_STDLIB)

        worker_init = WorkerInit(worker_config=worker_config,
                input_queue=input_queue, output_queue=output_queue)

        page_crawler = PageCrawler(worker_init)

        return page_crawler, url_split


    def test_404(self):
        urlopen = get_url_open()
        import socket
        url = self.get_url("/does_not_exist.html")
        response = open_url(urlopen, url, 5, socket.timeout)

        self.assertEqual(404, response.status)
        self.assertTrue(response.exception is not None)

    def test_200(self):
        urlopen = get_url_open()
        import socket
        url = self.get_url("/index.html")
        response = open_url(urlopen, url, 5, socket.timeout)

        self.assertEqual(200, response.status)
        self.assertTrue(response.exception is None)

    def test_301(self):
        urlopen = get_url_open()
        import socket
        url = self.get_url("/sub")
        response = open_url(urlopen, url, 5, socket.timeout)

        self.assertEqual(200, response.status)
        self.assertTrue(response.is_redirect)

    def test_crawl_page(self):
        page_crawler, url_split = self.get_page_crawler("/index.html")
        page_crawl = page_crawler._crawl_page(WorkerInput(url_split, True))

        self.assertEqual(200, page_crawl.status)
        self.assertTrue(page_crawl.is_html)
        self.assertFalse(page_crawl.is_timeout)
        self.assertFalse(page_crawl.is_redirect)
        self.assertTrue(page_crawl.exception is None)

        a_links = [link for link in page_crawl.links if link.type == 'a']
        img_links = [link for link in page_crawl.links if link.type == 'img']
        script_links = [link for link in page_crawl.links if link.type == 'script']
        link_links = [link for link in page_crawl.links if link.type == 'link']

        self.assertEqual(5, len(a_links))
        self.assertEqual(1, len(img_links))
        self.assertEqual(1, len(script_links))
        self.assertEqual(1, len(link_links))

    def test_crawl_resource(self):
        page_crawler, url_split = self.get_page_crawler("/sub/small_image.gif")
        page_crawl = page_crawler._crawl_page(WorkerInput(url_split, True))

        self.assertEqual(200, page_crawl.status)
        self.assertFalse(page_crawl.links)
        self.assertFalse(page_crawl.is_html)
        self.assertFalse(page_crawl.is_timeout)
        self.assertFalse(page_crawl.is_redirect)
        self.assertTrue(page_crawl.exception is None)

    def test_base_url(self):
        page_crawler, url_split = self.get_page_crawler("/alone.html")
        page_crawl = page_crawler._crawl_page(WorkerInput(url_split, True))

        self.assertEqual(1, len(page_crawl.links))
        self.assertEqual('http://www.example.com/test.html',
                page_crawl.links[0].url_split.geturl())

    def test_crawl_404(self):
        page_crawler, url_split = self.get_page_crawler("/sub/small_image_bad.gif")
        page_crawl = page_crawler._crawl_page(WorkerInput(url_split, True))

        self.assertEqual(404, page_crawl.status)
        self.assertFalse(page_crawl.links)
        self.assertFalse(page_crawl.is_html)
        self.assertFalse(page_crawl.is_timeout)
        self.assertFalse(page_crawl.is_redirect)

    def test_page_crawler(self):
        page_crawler, url_split = self.get_page_crawler("/index.html")
        input_queue = page_crawler.input_queue
        output_queue = page_crawler.output_queue

        input_queue.put(WorkerInput(url_split, True))
        input_queue.put(WORK_DONE)
        page_crawler.crawl_page_forever()

        page_crawl = output_queue.get()

        self.assertEqual(200, page_crawl.status)
        self.assertTrue(len(page_crawl.links) > 0)

    def test_site_thread_crawler_plain(self):
        url = self.get_url("/index.html")
        sys.argv = ['pylinkchecker', url]
        config = Config()
        config.parse_config()

        crawler = ThreadSiteCrawler(config)
        crawler.crawl()

        site = crawler.site
        self.assertEqual(11, len(site.pages))
        self.assertEqual(1, len(site.error_pages))

