"""
Module for handling HDF5 dataset.
Based on hdf5 datawrapper from qtlab originally by Reinier Heeres and
Wolfgang Pfaff and hdf5_data.py from PycQED module.
@yifan 
"""
import os
import time
import h5py
import numpy as np
import logging as log
from uncertainties import UFloat
########################################
#          helper function
########################################
def encode_to_utf8(s):
    """
    Required because h5py does not support python3 strings
    """
    # converts byte type to string because of h5py datasaving
    if isinstance(s, str):
        s = s.encode("utf-8")
    # If it is an array of value decodes individual entries
    elif isinstance(s, (np.ndarray, list, tuple)):
        s = [s.encode("utf-8") for s in s]
    return s

def RepresentsInt(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

def write_dict_to_hdf5(data_dict: dict, entry_point, group_overwrite_level: int = np.inf):
    """
    Arguments:
        data_dict (dict): dictionary to write to hdf5 file
        entry_point (hdf5 group.file) : location in the nested hdf5 structure where to write to.
        group_overwrite_level(int) ： wheter to overwrite excited level, e.g 0 for overwhrting hdf5 group
    """
    for key, item in data_dict.items():
        if isinstance(item, (str, float, int, bool, np.number, np.float_, np.int_, np.bool_)):
            try:
                entry_point.attrs[key] = item
            except Exception as e:
                print("Exception occurred while writing"
                    " {}:{} of type {} at entry point {}".format(key, item, type(item), entry_point))
                log.warning(e)
        
        elif isinstance(item, np.ndarray):
            entry_point.create_dataset(key, data=item)
        elif item is None:
            # as h5py does not support saving None as attribute
            # I create special string, note that this can create
            # unexpected behaviour if someone saves a string with this name
            entry_point.attrs[key] = "NoneType:__None__"

        elif isinstance(item, dict):
            
            # converting key to string is to make int dictionary keys work
            str_key = str(key)
            if str_key not in entry_point.keys():
                entry_point.create_group(str_key)
            
            elif group_overwrite_level < 1:
                log.debug("Overwriting hdf5 group: {}".format(str_key))
                del entry_point[str_key]
                entry_point.create_group(str_key)

            write_dict_to_hdf5(
                data_dict=item,
                entry_point=entry_point[str_key],
                group_overwrite_level=group_overwrite_level - 1,
            )

        elif isinstance(item, UFloat):
            str_key = str(key)
            if str_key not in entry_point.keys():
                entry_point.create_group(str_key)
            
            elif group_overwrite_level < 1:
                log.debug("Overwriting hdf5 group: {}".format(str_key))
                del entry_point[str_key]
                entry_point.create_group(str_key)

            new_item = {"nominal_value": item.nominal_value, "std_dev": item.std_dev}
            write_dict_to_hdf5(data_dict=new_item, entry_point=entry_point[str_key], group_overwrite_level=group_overwrite_level - 1,)

        elif isinstance(item, (list, tuple)):
            if len(item) > 0:
                
                elt_type = type(item[0])

                # Lists of a single type, are stored as an hdf5 dset
                if (
                    all(isinstance(x, elt_type) for x in item)
                    and not isinstance(item[0], dict)
                    and not isinstance(item, tuple)
                ):
                    if isinstance(item[0], (int, float, np.int32, np.int64)):
                        entry_point.create_dataset(key, data=np.array(item))
                        entry_point[key].attrs["list_type"] = "array"

                    # strings are saved as a special dtype hdf5 dataset
                    elif isinstance(item[0], str):
                        dt = h5py.special_dtype(vlen=str)
                        data = np.array(item)
                        data = data.reshape((-1, 1))
                        ds = entry_point.create_dataset(key, (len(data), 1), dtype=dt)
                        ds.attrs["list_type"] = "str"
                        ds[:] = data
                    else:
                        # For nested list we don't throw warning, it will be
                        # recovered in case of a snapshot
                        warn_msg = (
                            'List of type "{}" for "{}":"{}" not '
                            "supported, storing as string".format(elt_type, key, item)
                        )
                        if elt_type is list:
                            log.debug(warn_msg)
                        else:
                            log.warning(warn_msg)

                        entry_point.attrs[key] = str(item)
                
                # Storing of generic lists/tuples
                else:
                    if key not in entry_point.keys():
                        entry_point.create_group(key)
                    elif group_overwrite_level < 1:
                        log.debug("Overwriting hdf5 group: {}".format(key))
                        del entry_point[key]
                        entry_point.create_group(key)

                    # N.B. item is of type list
                    list_dct = {
                        "list_idx_{}".format(idx): entry
                        for idx, entry in enumerate(item)
                    }
                    group_attrs = entry_point[key].attrs
                    if isinstance(item, tuple):
                        group_attrs["list_type"] = "generic_tuple"
                    else:
                        group_attrs["list_type"] = "generic_list"
                    
                    group_attrs["list_length"] = len(item)
                    write_dict_to_hdf5(
                        data_dict=list_dct,
                        entry_point=entry_point[key],
                        group_overwrite_level=group_overwrite_level - 1,
                    )
            else:
                # as h5py does not support saving None as attribute
                entry_point.attrs[key] = "NoneType:__emptylist__"

        else:
            log.warning(
                'Type "{}" for "{}" (key): "{}" (item) at location {} '
                "not supported, "
                "storing as string".format(type(item), key, item, entry_point)
            )
            entry_point.attrs[key] = str(item)

def read_dict_from_hdf5(data_dict: dict, entry_point):
    """
    Reads a dictionary from an hdf5 file or group that was written using the
    corresponding "write_dict_to_hdf5" function defined above.

    Arguments:
        data_dict (dict):
                dictionary where we place all items that are read out from the hdf5 file entry_point.
                This argument exists because it allows nested calls of this
                function to add the data to an existing data_dict.
        entry_point  (hdf5 group):
                hdf5 file or group from which to read.
    """
    # if 'list_type' not in entry_point.attrs:
    for key, item in entry_point.items():
        if RepresentsInt(key):
            key = int(key)
        if isinstance(item, h5py.Group):
            data_dict[key] = {}
            data_dict[key] = read_dict_from_hdf5(data_dict[key], item)
        else:  # item either a group or a dataset
            if "list_type" not in item.attrs:
                data_dict[key] = item[()]  # changed deprecated item.value => item[()]
            elif item.attrs["list_type"] == "str":
                # lists of strings needs some special care, see also
                # the writing part in the writing function above.
                list_of_str = [
                    x[0] for x in item[()]
                ]  # changed deprecated item.value => item[()]
                data_dict[key] = list_of_str
            elif item.attrs["list_type"] == "array":
                data_dict[key] = list(
                    item[()]
                )  # changed deprecated item.value => item[()]
            else:
                data_dict[key] = list(
                    item[()]
                )  # changed deprecated item.value => item[()]
    for key, item in entry_point.attrs.items():
        if isinstance(item, str):
            # Extracts "None" as an exception as h5py does not support
            # storing None, nested if statement to avoid elementwise
            # comparison warning
            if item == "NoneType:__None__":
                item = None
            elif item == "NoneType:__emptylist__":
                item = []
        data_dict[key] = item

    if "list_type" in entry_point.attrs:
        if (
            entry_point.attrs["list_type"] == "generic_list"
            or entry_point.attrs["list_type"] == "generic_tuple"
        ):
            list_dict = data_dict
            data_list = []
            for i in range(list_dict["list_length"]):
                data_list.append(list_dict["list_idx_{}".format(i)])

            if entry_point.attrs["list_type"] == "generic_tuple":
                return tuple(data_list)
            else:
                return data_list
        else:
            raise NotImplementedError(
                'cannot read "list_type":"{}"'.format(entry_point.attrs["list_type"])
            )
    return data_dict

def extract_pars_from_datafile(param_spec: dict, filepath: str = None, entry_point = None) -> dict:
    """
    Extract corresponding parameters from an hdf5 datafile based on the dictionary "param_spec"

    Arguments:
        filepath (str)
            tilepath of the hfd5 datafile.

        param_spec (dict)
            specification of parameters to extract.
                key: name used to store the extracted entry
                value: tuple consiting of "/" separated parameter path
                    and attribute/dataset specificiation.
                    The attribute/dataset specification is
                    "attr:attribute_name", "dset", "attr:all_attr", or "group"
                    "group" allows to recursively extract all the tree in
                    the group

            example param_spec
                param_spec = {
                    'T1': ('Analysis/Fitted Params F|1>/tau', 'attr:value'),
                    'uT1': ('Analysis/Fitted Params F|1>/tau', 'attr:stderr'),
                    'data': ('Experimental Data/Data', 'dset'),
                    'timestamp': ('MC settings/begintime', 'dset'),
                    'qois': ('Analysis/quantities_of_interest', 'group')}

    Return:
        param_dict (dict)
            dictionary containing the extracted parameters.
    """
    if filepath is not None:
        param_dict = {}
        f = h5py.File(filepath, "r")
        with h5py.File(filepath, "r") as f:
            for par_name, par_spec in param_spec.items():
                try:
                    entry = f[par_spec[0]]
                    
                    if par_spec[1].startswith("dset"):
                        param_dict[par_name] = entry[()]  # deprecated syntax: entry.value
                    elif par_spec[1].startswith("attr:all_attr"):
                        param_dict[par_name] = dict()
                        for attribute_name in entry.attrs.keys():
                            param_dict[par_name][attribute_name] = entry.attrs[attribute_name]
                    elif par_spec[1].startswith("attr"):
                        param_dict[par_name] = entry.attrs[par_spec[1][5:]]
                    elif par_spec[1].startswith("group"):
                        # This should allow to retrieve the entire tree under a certain
                        # as a dictionary
                        new_dict = dict()
                        param_dict[par_name] = read_dict_from_hdf5(new_dict, entry_point=entry)
                    else:
                        raise ValueError(
                            "Parameter spec `{}` not recognized".format(par_spec[1])
                        )
                except Exception as err:
                    raise err

    elif (filepath is None) and (entry_point is not None):
        for par_name, par_spec in param_spec.items():
                try:
                    f = entry_point
                    entry = f[par_spec[0]]
                    
                    if par_spec[1].startswith("dset"):
                        param_dict[par_name] = entry[()]  # deprecated syntax: entry.value
                    elif par_spec[1].startswith("attr:all_attr"):
                        param_dict[par_name] = dict()
                        for attribute_name in entry.attrs.keys():
                            param_dict[par_name][attribute_name] = entry.attrs[attribute_name]
                    elif par_spec[1].startswith("attr"):
                        param_dict[par_name] = entry.attrs[par_spec[1][5:]]
                    elif par_spec[1].startswith("group"):
                        # This should allow to retrieve the entire tree under a certain
                        # as a dictionary
                        new_dict = dict()
                        param_dict[par_name] = read_dict_from_hdf5(new_dict, entry_point=entry)
                    else:
                        raise ValueError(
                            "Parameter spec `{}` not recognized".format(par_spec[1])
                        )
                except Exception as err:
                    raise err
        
    return param_dict
########################################
#           class 
########################################
class DateTimeGenerator(object):
    """
    Class to generate filenames / directories based on the date and time.
    """

    def __init__(self, timesubdir: bool = False, timefilename: bool = False):
        """
        Arguments:
        timesubdir(bool): whether to create a subdirectory for the time
        timefilename(bool): whether to create time tag in the filename 
        """
        self.timesubdir = timesubdir
        self.timefilename = timefilename

    def create_data_dir(self, datadir: str, name: str = None, ts=None, datesubdir: bool = True, timesubdir: bool = False):
        """
        Create and return a new data directory.

        Arguments:
            datadir (string) : base directory
            name (string) : optional name of measurement
            ts (time.localtime()) : timestamp which will be used
                if timesubdir=True
            datesubdir (bool) : whether to create a subdirectory for the date
            timesubdir (bool) : whether to create a subdirectory for the time

        Return:
            The directory to place the new file in
        """

        path = datadir
        if ts is None:
            ts = time.localtime()
        if datesubdir:
            path = os.path.join(path, time.strftime("%Y%m%d", ts))
        
        if timesubdir or self.timesubdir:
            tsd = time.strftime("%H%M%S", ts)
            timestamp_verified = False
            counter = 0
            
            # Verify if timestamp is unique by seeing if the folder exists
            while not timestamp_verified:
                counter += 1
                try:
                    measdirs = [d for d in os.listdir(path) if d[:6] == tsd]
                    if len(measdirs) == 0:
                        timestamp_verified = True
                    else:
                        # if timestamp not unique, add one second
                        # This is quite a hack
                        ts = time.localtime((time.mktime(ts) + 1))
                        tsd = time.strftime("%H%M%S", ts)
                    if counter >= 3600:
                        raise Exception()
                except OSError as err:
                    if "cannot find the path specified" in str(err):
                        timestamp_verified = True
                    elif "No such file or directory" in str(err):
                        timestamp_verified = True
                    else:
                        raise err
            if name is not None:
                path = os.path.join(path, tsd + "_" + name)
            else:
                path = os.path.join(path, tsd)  

        return path

    def new_filename(self, data_obj, path):
        """
        Return a new filename, based on name and timestamp.
        
        Arugments:
            data_obj (hdf5.File) : the hdf5 datafile object
            path (str) : the directory to place the new file in 

        Return:
        the full path of the hdf5 file 
        """
        
        path = self.create_data_dir(path, name=data_obj._name, ts=data_obj._localtime)
        
        if self.timefilename is True: 
            if data_obj._localtime is not None: 
                ts=data_obj._localtime
            else: 
                ts = time.localtime()
            
            tsd = time.strftime("%H%M%S", ts)
            timestamp_verified = False
            counter = 0

            # Verify if timestamp is unique by seeing if the folder exists
            while not timestamp_verified:
                counter += 1
                try:
                    measdirs = [d for d in os.listdir(path) if d[:6] == tsd]
                    if len(measdirs) == 0:
                        timestamp_verified = True
                    else:
                        # if timestamp not unique, add one second
                        # This is quite a hack
                        ts = time.localtime((time.mktime(ts) + 1))
                        tsd = time.strftime("%H%M%S", ts)
                    if counter >= 3600:
                        raise Exception()
                except OSError as err:
                    if "cannot find the path specified" in str(err):
                        timestamp_verified = True
                    elif "No such file or directory" in str(err):
                        timestamp_verified = True
                    else:
                        raise err

            filename = "%s_%s.hdf5" % (tsd, data_obj._name)
        else: 
            filename = "%s.hdf5" % (data_obj._name)
        
        return os.path.join(path, filename)

class DatasetFile(h5py.File):
    """ 
    Create the hdf5 file in the date directory (or time subdirectory) in the base path of "datadir" 
    """
    def __init__(self, name: str, datadir: str, timesubdir: bool = False, timefilename: bool = False):
        """
        Creates an empty data set including the file, for which the currently
        set file name generator is used.

        Arguments:
            name (str) : base name of the file
            datadir (str) : A base path where the hdf5file will be created in its subdirectory 
                using the standard timestamp structure
        """
        self._timesubdir = timesubdir
        self._timefilename = timefilename
        self._name = name
        
        self._localtime = time.localtime()
        self._timestamp = time.asctime(self._localtime)
        self._timemark = time.strftime("%H%M%S", self._localtime)
        self._datemark = time.strftime("%Y%m%d", self._localtime)

        self.filepath = DateTimeGenerator(timesubdir=self._timesubdir, timefilename=self._timefilename).new_filename(self, path=datadir)
        self.folder, self._filename = os.path.split(self.filepath)
        
        if not os.path.isdir(self.folder):
            os.makedirs(self.folder)
        super(DatasetFile, self).__init__(self.filepath, "a")
        self.flush()
