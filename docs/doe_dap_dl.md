# doe_dap_dl Package

This package contains the DAP module and wraps all other modules to make importing easy. Information on the plotting module is in plot/README.md. For more information on the DAP module, keep reading.

## DAP Module

The DAP module is a high-level interface that allows the programmer to use our API to authenticate, search, and download the data they want in very few lines of code.

## Installation

The doe_dap_dl package can be installed via pip: `pip install doe-dap-dl`

## Setup

The following examples demonstrate how to download data via WDH.

First, import the main module:

```python
from doe_dap_dl import DAP
```

Then, create an instance of the `DAP` class. The constructor takes one required argument: the hostname of the service from which you want to download data.

```python
wdh = DAP('wdh.energy.gov')
```

And that's it! Setup is complete. All future methods will revolve around this `wdh` object. The constructor also accepts the following optional arguments

- `cert_path` (str): path to authentication certificate file.
- `save_cert_dir` (str): Path to directory where certificates are stored.
- `download_dir` (str): Path to directory where files will be downloaded.
- `quiet` (bool): suppresses output print statemens. Useful for scripting. Defaults to False.
- `spp` (bool): If this is a dap for the Solid Phase Processing data. Defaults to False.
- `confirm_downloads` (bool): Whether or not to confirm before downloading. Defaults to True.

## Authentication

Authentication is simple. This module supports both __basic__ and __certificate__ authentication protocols. The basic method does not use a certificate, expires more quickly, and does not support two-factor authentication. __Proper authentication is required to use this module.__

### Certificates

The default name for an authetication certificate is `.<host name>.cert`, for example `.wdh.energy.gov.cert`. The following is the precedence of the different ways to provide a certificate's location.

1. `cert_path`
2. If `save_cert_dir` was provided, `DAP` will look for a certificate at `<save_cert_dir>/.<host name>.cert`
3. If the environment variable `DAP_CERT_DIR` exists, `DAP` will look for a certificate at `$DAP_CERT_DIR/.<host name>.cert`
4. Otherwise, `DAP` will look for a certificate at `~/doe_dap_dl/certs/.<host name>.cert`

If the certificate is valid, the module will renew it. If you don't have a valid certificate, you will have to authenticate via one of the following methods:

#### `wdh.setup_basic_auth()`

Creates authentication with a username and password. The arguments are optional, but the module will prompt for them if omitted.

#### `wdh.setup_cert_auth()`

Creates authentication with a certificate that can be used for future authentication. The certificate is stored in a file named `.<host name>.cert` (e.g. `.wdh.energy.gov.cert`). Returns whether or not a valid certificate was created.

#### `wdh.setup_two_factor_auth()`

Creates a certificate, but with two-factor authentication. The authcode is the 6-digit password code from Google Authenticator. This is the highest authentication level available, and is necessary to search for and download certain datasets. The certificate is stored in a file named `.<host name>.cert`. Returns whether or not a valid certificate was created.

Certificates last 24 hours before a new one must be created, and they must be renewed every hour. You can renew your certificate by using `wdh.renew_certificate()`, which returns a boolean representing whether renewing the certificate was successful. You can pass `quiet=True` to supress messages from this function.

### Searching for Files

To search for files, one must first construct a filter. Below is an example filter.

```python
filter = {
    'Dataset': 'wfip2/lidar.z01.b0',
    'date_time': {
        'between': ['20160101000000', '20160104000000']
    },
    'file_type': 'nc'
}
```

The documentation for constructing the filter argument can be found in `docs/download-README.md`

Now simply call this function:

#### `wdh.search(filter_arg, table='inventory', latest=True)`

The `'inventory'` option returns a list of files that match the filter. Filters that return large lists of files may time out, or return an empty list (despite the query matching many files). To avoid this, you can request an accounting of files by calling the function with `table='stats'`.

By default, only the latest files are considered for the search. If you'd like to include older files, you can use `latest=False`. Old files may not be downloadable.

### Downloading Files

There are three functions you can use to download files using this module.

#### Download with a list of files

An inventory search returns a list of files. These can be provided to the following function:

#### `wdh.download_files(files, path='/var/tmp/', replace=False)`

The path specifies where the module will download files. The replace flag determines whether the module should replace files that already exist in the download directory. By default, the module will not replace existing files.

##### Example

```python
filter = {
    'Dataset': 'wfip2/lidar.z04.a0',
    'date_time': {
        'between': ['20151001000000', '20151004000000']
    },
    'file_type': 'nc'
}

file_names = wdh.search(filter, table='Inventory')
files = wdh.download_files(file_names)
```

All the download functions return a list of paths to the downloaded files.

#### Download files directly from a search

Inventory searches fail with large numbers of files. This method will avoid creating a list of files and instead download using a search query. The module will prompt you to confirm that you want to download the files, although it won't say how much space the files will take up, so caution is recommended.

The DAP function is:

#### `wdh.download_search(filter_arg, path='/var/tmp/', force=False)`

##### Example

```python
filter = {
    'Dataset': 'wfip2/lidar.z04.a0',
    'date_time': {
        'between': ['20151001000000', '20151004000000']
    },
    'file_type': 'nc'
}

files = wdh.download_search(filter)
```

Provided with a [filter argument](https://github.com/a2edap/dap-py/blob/master/a2e/download-README.md), search the Inventory table and download the files in s3. I heard a rumor through the grapevine that only files in s3 will be downloaded, so if you think some data could be someone else, use the next download method.

#### Download by placing an order

Placing an order is required to download files that are not in s3. The following function takes a filter like `download_search()` but places an order before downloading.

#### `wdh.download_with_order(filter_arg, path='/var/tmp/', page_size=100, force=False)`

Like `download_search()`, the code will prompt you to confirm that you want to download the files.

```python
filter = {
    'Dataset': 'wfip2/lidar.z04.a0',
    'date_time': {
        'between': ['20151001000000', '20151004000000']
    },
    'file_type': 'nc'
}

wdh.download_with_order(filter)
```
---

### Download Using an Existing Order(s)
If you already have an order ID, you can use the following method:
#### `wdh.download_orders(order_ids, path='/var/tmp/', page_size=100, replace=False)`
- `order_ids`: A list of order IDs to retrieve download URLs.
- `path`: Specifies where files will be downloaded. Defaults to `/var/tmp/`.
- `page_size`: The number of file links to generate for request to the database.
    Lowering this value will cause downloads to take longer, but will fix timeout issues.
    Conversely, raising it will cause downloads to go faster, but may cause the API endpoint to time out. Defaults to 100.
- `replace`: Determines whether existing files should be replaced. Defaults to `False`.

This method automatically fetches download URLs from the provided order IDs, confirms the user wants to proceed, and downloads files.

##### Example:
```python
wdh.download_orders(
    order_ids=["order_id"], 
    path="/var/tmp/",
    replace=False
)
```

# Filtering

## Usage

### File Attributes

When a file is stored by the WDH system, a number of metadata attributes for that file are stored. request-data allows you to query on these attributes to retrieve specific data files. Along with values added by the system, the dot-delimited filename is parsed into attributes which can be used for data access. These attributes are named based on the configuration for the project. Arbitrary values that are not registered in the project config may also be stored in the file name. The first unregistered value will be stored as `ext1`, the second `ext2`, the third `ext3`, and so on.

Example filter that finds csv files where the unregistered attribute `ext1` is either wind or conductivity:

```json
{
    "Dataset": "buoy/buoy.z05.00",
    "date_time": {
        "between": ["20201008000000", "20201010000000"]
    },
    "file_type": "csv",
    "ext1" : ["wind", "conductivity"]
}
```

### Output Format Parameters

Format parameters act as modifiers for the output of request-data, but do not effect the data query results.

Valid format parameters are:

| Name          | Purpose       | Values|
| ------------- | ------------- | ----- |
| output        | Determines the format of the output filename-URL mapping. <ul><li>json - JSON dictionary of filenames to URLs</li><li>html - an HTML page with filename links that point to the download URL. If the `output` parameter isn't passed, this is the default mode</li><li>txt - A list of file URLs, delimited by newlines</li></ul>| json, html, txt |
| dryrun        | If the dryrun flag is present, the request will return file names, but download urls will not be generated | true, false |

### Query Parameters
Query parameters filter and control which data URLs are returned from request-data. A query parameter is an arbitrary key-value pair, where the key should be the name of a metadata attribute of one or more data files. Of the files with that metadata attribute, those which have a value matching the parameter value are returned. Query parameters can be [extended](#operators) with operations other than basic equality. All requests must have, at minimum, a Dataset parameter. Query parameters and their values are case sensitive. Every file has certain guaranteed parameters that are listed below:

<a name="param_table"></a>

| Name          | Explanation   | Example Values / Value Format|
| ------------- | ------------- | ----- |
| Dataset | Defined as the project name, a forward slash, and a dot-delimited list of every attribute in a data file name before the data date/time, the Dataset is required for every request. It is the broadest way to address a set of files with request-data | project/class.instance.level|
| data_date | The date parameter from the file name| YYYYMMDD |
| data_time | The time parameter from the file name| HHMMSS |
| date_time | The time and date parameters from the file name| YYYYMMDDHHMMSS |
| file_type | The extension of the file | txt, cdf, png |
| iteration | The version of the file | 0 1 2 |
| latest | A boolean that is set to True only for the latest iteration of the file | true, false |
| size | The size of the file in bytes | 30435 |

To find a full listing of the stored attributes for a given file or set of files, use the [get-info](../get-info/README.md) method.

### Creating Queries

To request data from request-data, you must create and POST a JSON document made up of query parameter key-value pairs. By default, basic equality is used to match documents, however, several advanced operators are supported. These operators can be applied to almost any attribute multiple times. The only exceptions are date_time, which can only filtered on once in a query, and Dataset, which cannot use special operators at all.

#### Basic Equality

A query that uses only basic single-value equality might look like this:

```json
{
    "output": "json",
    "filter": {
        "Dataset": "wfip2/lidar.z09.00",
        "data_date": "20160704",
        "file_type": "png"
    }
}
```

The output format is specified as JSON, each file attribute in the `filter` has a single string value that file metadata attribute values will have to match exactly.<br>This query will return all png images collected by the wfip2/lidar.z09.00 dataset on the fourth of July, 2016.<br>

#### Operators

Using operators from the table below, it is possible to extend the query syntax as follows in the example below, using the greater than operator and equals operator:

```json
{
    "output": "json",
    "filter": {
        "Dataset": "wfip2/lidar.z09.00",
        "file_type": "png",
        "data_date": {
            "gt": "20160704",
            "eq": "20160505"
        }
    }
}
```

The `data_date` value is now a JSON dictionary instead of a string. Each key in this dictionary should be an operation name, mapped to a value that the operation acts upon. The `gt` operation will be applied to the value `20160704`. The `eq` operation will be applied to the value `20160505`. The resulting query will now return all png images gathered by the wfip2/lidar.z09.00 dataset _after_ the fourth of July, 2016 and on the 5th of May, 2016.

Below is a table of supported operators:

| Operator      | Explanation   |
| ------------- | ------------- |
| begins_with   | The attribute must begin with the value|
| gt | The attribute must be greater than the value|
| gte | The attribute must be greater than or equal to the value|
| lt | The attribute must be less than the value|
| lte | The attribute must be less than or equal to the value |
| between | Requires a list of two values to be passed. The attribute must be between the two values (both the upper and lower bound are inclusive).|

#### Value Lists

It is possible to use a list of values anywhere that a single string value could be supplied. Instead of matching the single string, files matching any of the values in the list will be returned.
The query below shows the proper use of value lists:

```json
{
    "output": "json",
    "filter": {
        "Dataset": "wfip2/lidar.z09.00",
        "file_type": ["png", "txt"],
        "data_date": {
            "between": ["20160704", "20160707"],
            "eq": ["20160505", "20160405"]
        }
    }
}
```

The `file_type` attribute is expanded to match two possible values. `data_date` is filtered to match both a range of dates using the between operation, and two specific dates using the `eq` operation. The query will now match png and txt files that were gathered by the wfip2/lidar.z09.00 dataset from July 4th-7th, files from May 5th, and files from April 5th.

#### Optimization

Queries that filter on date_time can retrieve very specific ranges of data and will execute quickly. If your query involves time attributes, it can be beneficial to write the query to use the date_time attribute. Consider using a query like the following:

```json
{
    "data_time": {
        "between": ["20160505000000", "20160505240000"]
    }
}
```

instead of

```json
{
    "data_date": "20160505"
}
```

While both return the same file URLs, the first will execute much more quickly.

## Example

```python
from doe_dap_dl import DAP
wdh = DAP('wdh.energy.gov')

filter = {
    "Dataset": "wfip2/lidar.z09.00",
    "file_type": ["png", "gif", "jpeg"],
    "date_time": {
        "between": ["20160505000000", "20160507000000"]
    }
}

file_names = wdh.search(filter)
```
