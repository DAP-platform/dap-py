import imp
import os
import json
import base64
import re
from matplotlib.pyplot import quiver
from numpy import true_divide
import requests
from getpass import getpass
from .utils.scraper import get_api_url

class BadStatusCodeError(RuntimeError):
    def __init__(self, req):
        self.status_code = req.status_code
        try:
            self.reason = req.json()['message']
        except (KeyError, ValueError):
            self.reason = req.reason

    def __str__(self):
        return ((
            'Server Returned Bad Status Code\n'
            'Status Code: {}\n'
            'Reason: {}').format(self.status_code, self.reason)
        )


class dap:

    def __init__(self,host_URL, cert=None, quiet=False):
        """initializes connection with DAP server and performs authentication

        Args:
            host_URL (str): The url of the host, e.g. "livewire.energy.gov"
            cert (str, optional): path to authentication certificate file. Defaults to None.
            quiet (bool, optional): suppresses output print statemens. Useful for scripting Defaults to False.
        """
        self.host_URL = host_URL
        self._api_url = get_api_url(self.host_URL)
        self._quiet = quiet
        self._cert = cert
        self._auth = None

        if cert is None:
            self._read_cert()

        if self._cert_is_valid():
            self._create_cert_auth()
            self._print('Certificate is setup')
        else:
            self.setup_guest_auth()
            self._print('No authentication found. Using guest credentials...')

    def _print(self, *args, sep='', end='\n', file=None):
        if not self._quiet:
            for arg in args:
                print(arg, sep=sep, end=end, file=file)

    # --------------------------------------------------------------
    # Getting Authenticated
    # --------------------------------------------------------------

    def _request_cert(self, params):
        '''Request a certificate
        '''
        req = requests.put('{}/creds'.format(self._api_url), params=params)

        if req.status_code != 200:
            raise BadStatusCodeError(req)

        self._cert = json.loads(req.text)['cert']
        self._save_cert()

    def _create_cert_auth(self):
        '''Given an existing certificate, create an auth token
        '''
        if not self._cert:
            raise ValueError('cert cannot be None')

        self._auth = {
            "Authorization": "Cert {}".format(
                base64.b64encode(self._cert.encode("utf-8")).decode("ascii")
            )
        }

    def _request_cert_auth(self, params):
        '''Requests certificate and creates auth token
        '''
        try:
            self._request_cert(params)
            self._create_cert_auth()
        except BadStatusCodeError:
            self._print('Incorrect credentials')
            return
        except Exception as e:
            self._print(e)
            return
        self._print('Success!')
        return True

    def setup_basic_auth(self, username=None, password=None):
        '''Create the auth token without a certificate
        '''

        username = username or input('username: ')
        password = password or getpass('password: ')

        self._auth = {
            "Authorization": "Basic {}".format(base64.b64encode(
                ("{}:{}".format(username, password)).encode("utf-8")
            ).decode("ascii"))
        }
        # TODO: check if the creds are valid
        # without a certificate
        # should we try a query? low priority

    def setup_guest_auth(self):
        '''Just sets up basic auth as a guest
        '''
        self.setup_basic_auth('guest', 'guest')

    def setup_cert_auth(self, username=None, password=None):
        '''Given username and password request a
        cert token and generate an auth code
        '''
        if self._cert_is_valid():
            self._print('Valid certificate already created')
            return True

        params = {
            'username': username or input('username: '),
            'password': password or getpass('password: '),
        }

        self._request_cert_auth(params)
        return self._cert_is_valid()

    def setup_two_factor_auth(
        self, username=None, password=None, authcode=None
    ):
        '''Given username, password, and authcode, request a cert
        '''
        # we can't tell what kind of certification they
        # have with our current API, so we'll just make
        # them a new one

        params = {
            'username': username or input('username: '),
            'password': password or getpass('password: '),
            'authcode': authcode or getpass('authcode: '),
        }

        self._request_cert_auth(params)
        return self._cert_is_valid()

    def _renew_cert(self):
        '''Renews the certificate
        '''
        if not self._cert:
            raise ValueError('No certificate to renew')

        params = {
            'cert': self._cert,
            'action': 'renew',
        }

        resp = requests.put('{}/creds'.format(self._api_url), params=params)

        if resp.status_code != 200:
            raise BadStatusCodeError(resp)

        return 'cert' in resp.json()

    def _cert_is_valid(self):
        try:
            return self._renew_cert()
        except:  # noqa: E722
            return False

    def _save_cert(self, path=None):
        '''Save the cert to path
        '''
        if path is None:
            path = os.path.join(os.getcwd(), f'.{self.host_URL}.cert')
        with open(path, 'w') as cf:
            cf.write(self._cert)

    def _read_cert(self, path=None):
        '''Read from the path
        '''
        if path is None:
            path = os.path.join(os.getcwd(), f'.{self.host_URL}.cert')
        try:
            with open(path) as cf:
                self._cert = cf.read()
        except FileNotFoundError:
            return False
        return True

    # --------------------------------------------------------------
    # Search for Filenames
    # --------------------------------------------------------------

    def search(self, filter_arg, table='Inventory'):
        '''Search the table and return the matching file paths
        https://github.com/a2edap/tools/tree/master/lambda/api/get-info
        '''
        if not self._auth:
            raise Exception('Auth token cannot be None')

        req = requests.post(
            '{}/searches'.format(self._api_url),
            headers=self._auth,
            data=json.dumps({
                'source': table,
                'output': 'json',
                'filter': filter_arg,
                # 'with_inv_stats_beyond_limit':True
            })
        )

        if req.status_code != 200:
            self._print(req.text)
            raise BadStatusCodeError(req)

        req = req.json()
        # files = [x['Filename'] for x in req]
        return req

    # --------------------------------------------------------------
    # Placing Orders
    # --------------------------------------------------------------

    def _place_order(self, dataset, date_range=[], file_types=[], measurements=[]):
        '''Place an order and return the order ID
        '''
        if not self._auth:
            raise Exception('Auth token cannot be None')

        query = {}
        if date_range:
            query['date_time'] = {
                "between" : date_range
            }

        if file_types:
            query['file_type'] = file_types

        if measurements:
            query['ext1'] = measurements

        params = {
            "datasets": {
                f"{dataset}": {
                    "query": query
                }
            }
        }

        req = requests.put(
            '{}/orders'.format(self._api_url),
            headers=self._auth,
            data=json.dumps(params)
        )

        if req.status_code != 200:
            raise BadStatusCodeError(req)

        ID = json.loads(req.text)['id']
        return ID

    # --------------------------------------------------------------
    # Getting download URLs
    # --------------------------------------------------------------

    def _get_download_urls(self, ID, page_size=500):
        '''Given order ID, return the download urls
        '''
        if not self._auth:
            raise Exception('Auth token cannot be None')

        urls = []
        cursor = None

        while True:
            new_urls, cursor = self.__get_page_of_download_urls(ID, page_size, cursor)

            urls.extend(new_urls)
            self._print(f"Added {len(new_urls)} urls.")

            if cursor is None:
                self._print(f"No more pages of files, stopping after {len(urls)} urls.")
                return urls

            self._print("Another page detected, continuing...\n")

    def __get_page_of_download_urls(self, ID, page_size, cursor=None):
        '''Return one page of download urls given the order id, cursor and page size
        '''
        cursor_param = "" if cursor is None else f"&cursor={cursor}"

        #self._print(f"cursor param: {cursor_param}")

        req = requests.get(
            '{}/orders/{}/urls?page_size={}{}'.format(self._api_url, ID, page_size, cursor_param),
            headers=self._auth
        )

        if req.status_code != 200:
            raise BadStatusCodeError(req)

        response = json.loads(req.text)
        urls = response['urls']
        cursor = response['cursor']

        return urls, cursor

    # --------------------------------------------------------------
    # Download from URLs
    # --------------------------------------------------------------

    def _download(self, url, path):
        ''' Actually download the files
        '''
        req = requests.get(url, stream=True)
        if req.status_code != 200:
            raise BadStatusCodeError(req)
        while True:  # is this needed?
            with open(path, "wb") as fp:
                for chunk in req.iter_content(chunk_size=1024):
                    fp.write(chunk)
            self._print("Download successful! {}".format(path))
            break

    def _download_from_urls(self, urls, path='/var/tmp/', force=False):
        '''Given a list of urls, download them
        Returns the successfully downloaded file paths
        '''
        if not urls:
            raise Exception('No urls provided')

        downloaded_files = []
        self._print(f"Attempting to download {len(urls)} files...")
        # TODO: multi-thread this
        for url in urls:
            try:
                a = url.split('/')
                filename = a[5].split('?')[0]

                dataset = '{}.{}'.format(
                    a[4], '.'.join(a[5].split('.')[:3])
                )

                # /var/tmp/wfip2.lidar.z01.b0
                download_dir = os.path.join(path, dataset)
                os.makedirs(download_dir, exist_ok=True)
                # the final file path
                filepath = os.path.join(download_dir, filename)
            except:
                self._print(
                    'Incorrectly formmated file path in url: {}'.format(url)
                )
                continue

            if not force and os.path.exists(filepath):
                self._print(
                    'File: {} already exists, skipping...'.format(filepath)
                )
            else:
                try:
                    self._download(url, filepath)
                except BadStatusCodeError as e:
                    self._print('Could not download file: {}'.format(filepath))
                    self._print(e)
                    continue

            downloaded_files.append(filepath)

        self._print(f"Downloaded {len(downloaded_files)} files!")

        return downloaded_files

    # --------------------------------------------------------------
    # Place Order and Download
    # --------------------------------------------------------------

    def download_files(self, files, path='/var/tmp/', force=False):
        '''places order, gets download urls, downloads files
        '''
        if not files:
            self._print('No files provided')
            return

        try:
            ID = self._place_order(files)
        except BadStatusCodeError as e:
            self._print('Could not place order')
            self._print(e)
            return

        try:
            urls = self._get_download_urls(ID)
        except BadStatusCodeError as e:
            self._print('Could not get download urls')
            self._print(e)
            return

        try:
            downloaded_files = self._download_from_urls(
                urls, path=path, force=force
            )
        except Exception as e:
            self._print(e)
            return

        return downloaded_files

    # --------------------------------------------------------------
    #  Download All matching Search
    # --------------------------------------------------------------

    def _search_for_urls(self, filter_arg):
        '''uses the alternative api /downloads method
        to search the inventory table and return
        the download urls to files in s3
        '''
        if not self._auth:
            raise Exception('Auth token cannot be None')

        req = requests.post(
            '{}/downloads'.format(self._api_url),
            headers=self._auth,
            data=json.dumps(filter_arg)
        )

        if req.status_code != 200:
            raise BadStatusCodeError(req)

        urls = json.loads(req.text)['urls'].values()
        return urls

    def download_search(self, filter_arg, path='/var/tmp/', force=False):
        '''Uses the /downloads api method to download straight from
        the search without placing orders and downloading from there
        '''
        try:
            urls = self._search_for_urls({
                'output': 'json',
                'filter': filter_arg,
            })
        except BadStatusCodeError as e:
            self._print('Could not find download urls')
            self._print(e)
            return
        except Exception as e:
            self._print(e)
            return

        if not urls:
            self._print('No files found')
            return

        try:
            downloaded_files = self._download_from_urls(
                urls, path=path, force=force
            )
        except Exception as e:
            self._print(e)
            return
        return downloaded_files
