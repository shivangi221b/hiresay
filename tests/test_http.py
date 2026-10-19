"""Short-lived local integration server; no LinkedIn session or browser needed."""
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from hiresay.core import Store
from hiresay.collector import Collector
from hiresay.server import handler_for


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.server = ThreadingHTTPServer(('127.0.0.1',0),lambda *args:None)
        self.port = self.server.server_port
        self.server.RequestHandlerClass = handler_for(self.store,Collector(self.store),self.port)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self,path,body=None,headers=None):
        conn = http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        defaults = {'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}','X-HireSay':'local'}
        defaults.update(headers or {})
        conn.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None, defaults)
        response = conn.getresponse()
        status, data = response.status,response.read()
        conn.close()
        return status,data

    def test_local_state_and_settings(self):
        code, raw = self.request('/api/state')
        self.assertEqual(code,200)
        self.assertEqual(json.loads(raw)['posts'],[])
        self.assertEqual(self.request('/api/settings',{'lookback_hours':168})[0],200)
        self.assertEqual(self.store.settings()['lookback_hours'],168)
        self.assertEqual(self.request('/api/scan',{'hours':-1})[0],400)

    def test_remote_origin_rebinding_and_file_access_blocked(self):
        self.assertEqual(self.request('/api/settings',{'lookback_hours':168},{'Origin':'https://evil.test'})[0],403)
        self.assertEqual(self.request('/api/settings',{'lookback_hours':168},{'X-HireSay':''})[0],403)
        self.assertEqual(self.request('/api/state',headers={'Host':'evil.test'})[0],403)
        for path in ['/../hiresay/core.py','/browser-profile/Cookies','/hiresay.sqlite3']:
            self.assertEqual(self.request(path)[0],404)
        self.assertEqual(self.store.settings()['lookback_hours'],24)


if __name__ == '__main__':
    unittest.main()
