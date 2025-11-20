import base64
import json
import os
import requests
import sys
import traceback

from getpass import getpass
from pathlib import Path
from urllib.parse import urlparse, parse_qs


class BadStatusCodeError(RuntimeError):
    def __init__(self, req):
        self.status_code = req.status_code
        try:
            self.reason = req.json()["message"]
        except (KeyError, ValueError):
            self.reason = req.reason

    def __str__(self):
        return (
            "Server Returned Bad Status Code\n"
            f"Status Code: {self.status_code}\n"
            f"Reason: {self.reason}"
        )


class DAP:
    def __init__(
        self,
        host_URL,
        cert_path=None,
        save_cert_dir=None,
        download_dir=None,
        quiet=False,
        spp=False,
        confirm_downloads=True,
    ):
        """initializes connection with DAP server and performs authentication

        Args:
            host_URL (str): The url of the host, e.g. "livewire.energy.gov"
            cert_path (str, optional): path to authentication certificate file. Defaults to None.
            save_cert_dir (str, optional): Path to directory where certificates are stored. Defaults to None
            download_dir (str, optional): Path to directory where files will be downloaded. Defaults to None
            quiet (bool, optional): suppresses output print statemens. Useful for scripting. Defaults to False.
            spp (bool, optional): If this is a dap for the Solid Phase Processing data. Defaults to False.
            confirm_downloads (bool, optional): Whether or not to confirm before downloading. Defaults to True.
        """
        self.host_URL = host_URL
        if spp:
            self._api_url = (
                "https://13tl7mor8f.execute-api.us-west-2.amazonaws.com/prod"
            )
        elif "wdh" in self.host_URL or "a2e" in self.host_URL:
            self._api_url = "https://70d76sxu18.execute-api.us-west-2.amazonaws.com/prod"
        elif "livewire" in self.host_URL:
            self._api_url = "https://xkkcnw0931.execute-api.us-west-2.amazonaws.com/prod"

        self._quiet = quiet
        self.confirm_downloads = confirm_downloads
        self._cert_path = cert_path
        self._cert = None
        self._auth = None

        # set the certificate save and download paths.
        if save_cert_dir is None:
            save_cert_dir = os.getenv("DAP_CERT_DIR") or Path.home() / "doe_dap_dl/certs"
        self.save_cert_dir = save_cert_dir

        if download_dir is None:
            download_dir = (
                os.getenv("DAP_DOWNLOAD_DIR") or Path.home() / "doe_dap_dl/downloads"
            )
        self.download_dir = download_dir

        self.__create_dirs()

        if cert_path is None:
            self._cert_path = Path(self.save_cert_dir) / f".{self.host_URL}.cert"
        else:
            self._cert_path = cert_path

        self.__print(f"Looking for a certificate: {self._cert_path}...")
        found_cert = False
        if os.path.isfile(self._cert_path):
            self.__print("Found it!")
            found_cert = True
        else:
            self.__print("Certificate not found.")
            self.__print_setup_authentication()

        if found_cert:
            self.__read_cert()

            if self.renew_cert(quiet=True):
                self.__create_cert_auth_token()
                self.__print(
                    "Authenticaion successfully created using valid certificate."
                )
            else:
                self.__print("Certificate was invalid.")
                self.__print_setup_authentication()

    def __print(self, *args, sep="", end="\n", file=None):
        if not self._quiet:
            for arg in args:
                print(arg, sep=sep, end=end, file=file)

    def __create_dirs(self):
        Path(self.save_cert_dir).mkdir(parents=True, exist_ok=True)
        Path(self.download_dir).mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------------
    # Getting Authenticated
    # --------------------------------------------------------------

    def __validate_response(self, response, download_response=False):
        if response.status_code != 200:
            raise BadStatusCodeError(response)

        if download_response:
            return True

        text = response.text
        if "errorMessage" in text:
            error = text.split(",")[0].split("=")[1]
            self.__print(f"Error: {error}")
            return False

        return True

    def __request_cert(self, params):
        """Request a certificate"""
        response = requests.put(f"{self._api_url}/creds", params=params)

        if not self.__validate_response(response):
            return

        self._cert = json.loads(response.text)["cert"]
        self.__save_cert()

    def __create_cert_auth_token(self):
        """Given an existing certificate, create an auth token"""
        if not self._cert:
            raise ValueError("Could not create cert auth, missing certificate.")

        encoded_cert = base64.b64encode(self._cert.encode("utf-8")).decode("ascii")
        self._auth = {"Authorization": f"Cert {encoded_cert}"}

    def __request_cert_auth(self, params):
        """Requests certificate and creates auth token"""
        try:
            self.__request_cert(params)
            self.__create_cert_auth_token()
        except BadStatusCodeError:
            self.__print("Incorrect credentials")
            return False
        except Exception as e:
            self.__print(e)
            return False
        return True

    def setup_basic_auth(self):
        """Create an auth token without a certificate

        Args:
            username (str, optional): Username, if None it will prompt. Defaults to None.
            password (str, optional): Password, if None it will prompt. Defaults to None.
        """

        username = input("username: ")
        password = getpass("password: ")

        self.__print(f"Setting up authentication for user {username}...")

        user_pass_encoded = base64.b64encode(
            (f"{username}:{password}").encode("utf-8")
        ).decode("ascii")

        self._auth = {"Authorization": f"Basic {user_pass_encoded}"}
        self.__print(f"Authentication created for {username}.")
        # TODO: check if the creds are valid
        # without a certificate
        # should we try a query? low priority

    def setup_cert_auth(self):
        """Given username and password request a cert token and generate a
           certificate

        Args:
            username (str, optional): Username, if None it will prompt. Defaults to None.
            password (str, optional): Password, if None it will prompt. Defaults to None.

        Returns:
            bool: Whether the requested certificate was valid.
        """

        if self.renew_cert(quiet=True):
            self.__print("Valid certificate already created, it has been renewed.")
            return True

        params = {
            "username": input("username: "),
            "password": getpass("password: "),
        }

        self.__print(
            f"Setting up certificate authentication for user {params['username']}..."
        )

        if not self.__request_cert_auth(params):
            self.__print("Requesting a certificate failed.")
            return False

        valid = self.renew_cert(quiet=True)
        if valid:
            self.__print(
                f"Successfully set up certificate authentication for user {params['username']}."
            )
        else:
            self.__print(
                "Setting up certificate authentication failed: certificate was invalid."
            )
        return valid

    def setup_two_factor_auth(self):
        """Given a username, password, and 2 factor authentication code,
           generate a certificate with two factor auth permissions

        Args:
            username (str, optional): Username, if None it will prompt. Defaults to None.
            password (str, optional): Password, if None it will prompt. Defaults to None.
            authcode (str, optional): Two factor auth code, if None it will prompt. Defaults to None.

        Returns:
            bool: Whether the requested certificate was valid.
        """
        if self.renew_cert(quiet=True):
            self.__print("Valid certificate already created, it has been renewed.")
            return True

        params = {
            "username": input("username: "),
            "password": getpass("password: "),
            "authcode": getpass("authcode: "),
        }

        self.__print(
            f"Setting up two-factor authentication for user {params['username']}..."
        )

        if not self.__request_cert_auth(params):
            self.__print(f"Setting up two-factor authentication failed.")
            return False

        valid = self.renew_cert(quiet=True)
        if valid:
            self.__print(
                f"Successfully set up two-factor authentication for user {params['username']}."
            )
        else:
            self.__print(
                "Setting up two-factor authentication failed: created certificate was invalid."
            )
        return valid

    def renew_cert(self, quiet=False):
        """Renews the certificate"""
        if not self._cert:
            if not quiet:
                self.__print("No certificate to renew")
            return False

        if not quiet:
            self.__print("Renewing existing certificate...")

        params = {
            "cert": self._cert,
            "action": "renew",
        }

        resp = requests.put(f"{self._api_url}/creds", params=params)

        if resp.status_code != 200:
            if not quiet:
                self.__print(f"Request to renew certificate returned bad status code {resp.status_code}")
            return False

        if "cert" in resp.json():
            if not quiet:
                self.__print("Certificate successfully renewed")
            return True
        else:
            if not quiet:
                self.__print("Failed to renew certificate, it may be expired or invalid.")
            return False

    def __save_cert(self):
        """Save the cert to path"""
        path = Path(self.save_cert_dir) / f".{self.host_URL}.cert"
        with open(path, "w") as cf:
            cf.write(self._cert)
            self.__print(f"Saved certificate as {self._cert_path}")

    def __read_cert(self):
        """Read from the path"""
        try:
            with open(self._cert_path) as cf:
                self.__print(f"Reading certificate: {self._cert_path}...")
                self._cert = cf.read()
        except (OSError, IOError) as e:
            self.__print(f"There was a problem reading the certificate!")
            self.__print(traceback.format_exc())
            return False
        return True

    # --------------------------------------------------------------
    # Search for Filenames
    # --------------------------------------------------------------

    def search(self, filter_arg, table="inventory", latest=True):
        """Search the table and return the matching file information

        Args:
            filter_arg (dict): The filter argument. For information on how to construct this see download-README.md
            table (str, optional): Which table to query. Either 'inventory' or 'stats'. Defaults to 'inventory'.
            latest (bool, optional): Whether to only include the latest files. Defaults to True.

        Returns:
            list: The list of file information returned by the filter.
        """

        if not self.__check_for_auth(action="search"):
            return

        if "livewire" not in self.host_URL:
            filter_arg["latest"] = latest

        if "test" in self.host_URL and not table.endswith("-test"):
            self.__print(
                "You're trying to access data on a test server, but the table name doesn't include 'test', adding it."
            )
            table += "-test"

        # the dataset can be the only key in the filter
        if "test" in self.host_URL and len(filter_arg.keys()) > 1:
            if "Dataset" in filter_arg.keys():
                self.__print(
                    "A dataset can be the only parameter in the filter for a test server, removing the extras."
                )
                filter_arg = {"Dataset": filter_arg["Dataset"]}
            else:
                self.__print("No dataset provided.")
                return

        req = requests.post(
            f"{self._api_url}/searches",
            headers=self._auth,
            data=json.dumps(
                {
                    "source": table,
                    "output": "json",
                    "filter": filter_arg
                    # 'with_inv_stats_beyond_limit':True
                }
            ),
        )
        req.raise_for_status()

        return req.json()

    # --------------------------------------------------------------
    # Placing Orders
    # --------------------------------------------------------------

    def __place_order(self, dataset, filter_arg):
        """Place an order and return the order ID"""

        params = {"datasets": {f"{dataset}": {"query": filter_arg}}}

        response = requests.put(
            f"{self._api_url}/orders", headers=self._auth, data=json.dumps(params)
        )

        if not self.__validate_response(response):
            return

        ID = json.loads(response.text)["id"]

        return ID

    # --------------------------------------------------------------
    # Getting download URLs
    # --------------------------------------------------------------

    def __get_download_urls(self, ID, page_size=100):
        """Given order ID, return the download urls"""
        urls = []
        cursor = None

        while True:
            try:
                new_urls, cursor = self.__get_page_of_download_urls(
                    ID, page_size, cursor
                )
            except BadStatusCodeError as e:
                self.__print("Error getting page of download urls!")
                self.__print(e)
                # skip this page and stop trying
                break
            except Exception as e:
                self.__print("Unexpected error while fetching download urls")
                self.__print(e)
                break

            urls.extend(new_urls)
            self.__print(f"Added {len(new_urls)} urls.")

            if cursor is None:
                self.__print(
                    f"No more pages of files, stopping after {len(urls)} urls."
                )
                return urls

            self.__print("Another page detected, continuing...\n")

        return urls
    def __get_page_of_download_urls(self, ID, page_size, cursor=None):
        """Return one page of download urls given the order id, cursor and page size"""
        cursor_param = "" if cursor is None else f"&cursor={cursor}"

        # self._print(f"cursor param: {cursor_param}")

        response = requests.get(
            f"{self._api_url}/orders/{ID}/urls?page_size={page_size}{cursor_param}",
            headers=self._auth,
        )

        if not self.__validate_response(response):
            return

        response = json.loads(response.text)
        urls = response["urls"]
        cursor = response["cursor"]

        return urls, cursor

    # --------------------------------------------------------------
    # Download from URLs
    # --------------------------------------------------------------

    def __download(self, url, path):
        """Actually download the files"""
        response = requests.get(url, stream=True)

        if not self.__validate_response(response, download_response=True):
            return

        while True:  # is this needed?
            with open(path, "wb") as fp:
                for chunk in response.iter_content(chunk_size=1024):
                    fp.write(chunk)
            self.__print(f"Download successful! {path}")
            break

    def __download_from_urls(self, urls, path="/var/tmp/", replace=False):
        """Given a list of urls, download them
        Returns the successfully downloaded file paths
        """
        if not urls:
            raise Exception("No urls provided")

        downloaded_paths = []
        self.__print(f"Attempting to download {len(urls)} files...")
        downloaded = 0
        failed = 0
        skipped = 0
        # TODO: multi-thread this
        for url in urls:
            try:
                parsed_url = urlparse(url)
                query = parse_qs(parsed_url.query)
                if 'file' in query:
                    filename = query['file'][0]
                else:
                    filename = parsed_url.path.split("/")[-1]

                download_dir = path
                os.makedirs(download_dir, exist_ok=True)
                # the final file path
                filepath = os.path.join(download_dir, filename)
            except:
                self.__print(f"Incorrectly formatted file path in url: {url}")
                failed += 1
                continue

            if not replace and os.path.exists(filepath):
                self.__print(f"File: {filepath} already exists, skipping...")
                skipped += 1
            else:
                try:
                    self.__download(url, filepath)
                    downloaded_paths.append(filepath)
                    downloaded += 1
                except BadStatusCodeError as e:
                    self.__print(f"Could not download file: {filepath}")
                    self.__print(e)
                    failed += 1
                    continue

        self.__print(f"{downloaded} files downloaded, {failed} failed, {skipped} skipped")

        return downloaded_paths

    # --------------------------------------------------------------
    # Place Order and Download
    # --------------------------------------------------------------

    def download_files(self, files, path="/var/tmp/", replace=False):
        """Download a list a files

        Args:
            files (list): A list of files obtained via search()
            path (str, optional): The download path. Defaults to "/var/tmp/".
            replace (bool, optional): Whether to redownload and replace existing files. Defaults to False.

        Returns:
            list: The list of paths to the downloaded files.
        """
        if not self.__check_for_auth("download files"):
            return

        if not files:
            self.__print("No files provided.")

        filter = {
            "output": "json",
            "filter": None,
        }

        urls = []
        found = 0
        not_found = 0
        for f in files:
            filename = f["Filename"]
            dataset = f["Dataset"]

            filter["filter"] = {
                "Filename" : filename,
                "Dataset" : dataset,
            }
            if "date_time" in f:
                filter["filter"]["date_time"] = f["date_time"]

            response = requests.post(
                f"{self._api_url}/downloads",
                headers=self._auth,
                data=json.dumps(filter),
            )

            if not self.__validate_response(response):
                return

            url = json.loads(response.text)["urls"].values()

            # this should only return one url
            if len(url) != 1:
                self.__print(
                    f"found {len(url)} urls instead of one for file {filename}"
                )
                not_found += 1
            else:
                self.__print(f"found url for file: {filename}")
                found += 1

            # use extend in case somehow multiple files were found, this might not be necessary
            urls.extend(url)

        self.__print(f"found {found} files.")
        if not_found > 0:
            self.__print(
                f"Urls could not be found for {not_found} files, these files are most likely not hosted on s3 and should be downloaded via download_with_order()."
            )

        download = True
        if self.confirm_downloads:
            download = self.__proceed_prompt(f"Download {len(urls)} files (y/n)? ")

        if not download:
            return
        try:
            return self.__download_from_urls(urls, path=path, replace=replace)
        except Exception as e:
            self.__print(e)

    # --------------------------------------------------------------
    #  Download All matching Search
    # --------------------------------------------------------------

    def __search_for_urls(self, filter_arg):
        """uses the alternative api /downloads method
        to search the inventory table and return
        the download urls to files in s3
        """

        response = requests.post(
            f"{self._api_url}/downloads",
            headers=self._auth,
            data=json.dumps(filter_arg),
        )

        if not self.__validate_response(response):
            return

        urls = json.loads(response.text)["urls"].values()
        return urls

    def download_search(self, filter_arg, path="/var/tmp/", replace=False):
        """Download files straight from a search without placing an order

        Args:
            filter_arg (dict): The filter argument. For information on how to construct this see download-README.md
            path (str, optional): The download path. Defaults to '/var/tmp/'.
            replace (bool, optional): Whether to redownload and replace existing files. Defaults to False.

        Returns:
            list: The list of paths to the downloaded files.
        """
        if not self.__check_for_auth("download via search"):
            return
        try:
            urls = self.__search_for_urls(
                {
                    "output": "json",
                    "filter": filter_arg,
                }
            )
        except BadStatusCodeError as e:
            self.__print("Could not find download urls")
            self.__print(e)
            return
        except Exception as e:
            self.__print(e)
            return

        if not urls:
            self.__print("No files found")
            return

        download = True
        if self.confirm_downloads:
            download = self.__proceed_prompt(f"Download {len(urls)} files (y/n)? ")

        if download:
            try:
                downloaded_files = self.__download_from_urls(
                    urls, path=path, replace=replace
                )
            except Exception as e:
                self.__print(e)
                return
        else:
            return

        return downloaded_files

    def download_with_order(self, filter_arg, path="/var/tmp", page_size=100, replace=False):
        """Place an order and download files based on a query.

        filter_arg (dict): The filter argument. For information on how to construct this see download-README.md
        path (str, optional): The download path. Defaults to '/var/tmp/'.
        page_size (int, optional): The number of file links to generate for request to the database. 
            Lowering this value will cause downloads to take longer, but will fix timeout issues. 
            Conversely, raising it will cause downloads to go faster, but may cause the API endpoint to time out. Defaults to 100.
        replace (bool, optional): Whether to redownload and replace existing files. Defaults to False.

        Returns:
            list: The list of paths to the downloaded files.
        """

        if not self.__check_for_auth("download by placing an order"):
            return

        dataset = filter_arg["Dataset"]

        if not dataset:
            raise Exception("No dataset provided!")

        self.__print("Attempting to place an order for the data...")

        try:
            ID = self.__place_order(dataset, filter_arg)
        except BadStatusCodeError as e:
            self.__print("Could not place order")
            self.__print(e)
            return

        self.__print(f"Order placed! ID: {ID}")
        self.__print("Attempting to fetch download urls...")

        try:
            urls = self.__get_download_urls(ID, page_size=page_size)
        except BadStatusCodeError as e:
            self._print("Could not get download urls")
            self._print(e)
            return

        self.__print("Urls found!")

        download = True
        if self.confirm_downloads:
            download = self.__proceed_prompt(f"Download {len(urls)} files (y/n)? ")

        if download:
            try:
                downloaded_files = self.__download_from_urls(
                    urls, path=path, replace=replace
                )
            except Exception as e:
                self.__print(e)
                return
        else:
            return

        return downloaded_files
    
    def download_orders(self, order_ids, path="/var/tmp", page_size=100, replace=False):
        """
        Download files using existing order IDs.

        Args:
            order_ids (list): List of order IDs to fetch download URLs from.
            path (str, optional): The download path. Defaults to '/var/tmp'.
            page_size (int, optional): The number of file links to generate for request to the database. 
                Lowering this value will cause downloads to take longer, but will fix timeout issues. 
                Conversely, raising it will cause downloads to go faster, but may cause the API endpoint to time out. Defaults to 100.
            replace (bool, optional): Whether to redownload and replace existing files. Defaults to False.

        Returns:
            list: List of paths to the downloaded files.
        """

        if not self.__check_for_auth("download from existing orders"):
            return

        if not order_ids:
            raise ValueError("No order IDs provided!")

        all_downloaded_files = []

        for ID in order_ids:
            self.__print(f"Processing order ID: {ID}")
            self.__print("Fetching download URLs...")

            try:
                urls = self.__get_download_urls(ID, page_size=page_size)
            except BadStatusCodeError as e:
                self.__print(f"Could not get download URLs for order ID {ID}")
                self.__print(e)
                continue

            self.__print(f"Found {len(urls)} URLs for order ID {ID}")

            download = True
            if self.confirm_downloads:
                download = self.__proceed_prompt(f"Download {len(urls)} files from order {ID} (y/n)? ")

            if download:
                try:
                    downloaded_files = self.__download_from_urls(
                        urls, path=path, replace=replace
                    )
                    all_downloaded_files.extend(downloaded_files)
                except Exception as e:
                    self.__print(f"Error downloading files from order ID {ID}")
                    self.__print(e)
                    continue

        return all_downloaded_files

    def __proceed_prompt(self, prompt):
        while True:
            proceed = input(prompt)
            if proceed.lower() not in ("y", "n"):
                print("Enter either y or n")
            else:
                break

        return proceed == "y"

    def __check_for_auth(self, action=""):
        if not self._auth:
            self.__print_setup_authentication(action)
            return False
        return True

    def __print_setup_authentication(self, action=""):
        if action != "":
            start = f"You will need to authenticate to {action}."
        else:
            start = f"You will need to authenticate to use this module further."

        self.__print(f"{start} Set up authentication with setup_basic_auth(), setup_cert_auth(), or setup_two_factor_auth().")
        self.__print("More information available in the docs: https://github.com/DAP-platform/dap-py/blob/master/docs/doe_dap_dl.md")
