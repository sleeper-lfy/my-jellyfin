"""Retain native curl and delvewheel's sibling DLL directory on Windows."""
from PyInstaller.utils.hooks import collect_data_files,collect_dynamic_libs,collect_delvewheel_libs_directory

datas=collect_data_files('curl_cffi')
binaries=collect_dynamic_libs('curl_cffi')
datas,binaries=collect_delvewheel_libs_directory('curl_cffi',datas=datas,binaries=binaries)
hiddenimports=['_cffi_backend']
