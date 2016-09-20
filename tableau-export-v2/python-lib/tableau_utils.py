# -*- coding: utf-8 -*-
from tableausdk import *
from tableausdk.Extract import *
from tableausdk.Server import *
# Because of a bug in Tableau, we need to load Tableau before pandas.
# See http://community.tableau.com/thread/156790 for more info

import dataiku
import os
from dataiku.customrecipe import *
from datetime import datetime

import numpy as np
import pandas as pd

typeMap = {
    'tinyint': Type.INTEGER,
    'smallint':Type.INTEGER,
    'int':     Type.INTEGER,
    'bigint':  Type.INTEGER,
    'float':   Type.DOUBLE,
    'double':  Type.DOUBLE,
    'boolean': Type.BOOLEAN,
    'string':  Type.UNICODE_STRING,
    'date':    Type.DATETIME,
    'array':   Type.UNICODE_STRING,
    'map':     Type.UNICODE_STRING,
    'object':  Type.UNICODE_STRING
    }


def set_int(row, col, val):
    row.setInteger(col, int(val))


def set_long(row, col, val):
    row.setLongInteger(col, int(val))


def set_double(row, col, val):
    row.setDouble(col, float(val))


def set_str(row, col, val):
    if isinstance(val, float):
        if np.isnan(val):
            return
        else:
            row.setString(col, unicode(val)),
    else:
        row.setString(col, unicode(val))


def set_date(row, col, val):
    if pd.isnull(val):
        return
    row.setDateTime(col, val.year, val.month, val.day, val.hour, val.minute, val.second, val.microsecond)

fieldSetterMap = {
    'boolean':  lambda row, col, val: row.setBoolean(col, val),
    'tinyint':  set_int,
    'smallint': set_int,
    'int':      set_int,
    'bigint':   set_long,
    'float':    set_double,
    'double':   set_double,
    'date':     set_date,
    'string':   set_str,
    'array':    set_str,
    'map':      set_str,
    'object':   set_str
}


class TDEExport(object):
    @staticmethod
    def make_table_definition(schema):
        table_def = TableDefinition()
        table_def.setDefaultCollation(Collation.EN_GB)
        for col in schema:
            table_def.addColumn(col['name'], typeMap.get(type,Type.UNICODE_STRING))
        return table_def

    def __init__(self, tde_file_path, input_schema):
        self.tde_file_path = tde_file_path
        self.output_path = os.path.dirname(self.tde_file_path)
        self.input_schema = input_schema

        self.errors = 0
        self.nrows = 0

        print "Writing TDE file: %s" % self.tde_file_path
        ExtractAPI.initialize()
        self.extract = Extract(self.tde_file_path)
        assert(not self.extract.hasTable('Extract'))
        self.table_def = TDEExport.make_table_definition(self.input_schema)
        self.table = self.extract.addTable('Extract', self.table_def)

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        self.close();

    def close(self):
        self.extract.close()
        ExtractAPI.cleanup()
        if self.errors > 0:
            print "Encountered %d errors" % self.errors

    def insert_array_row(self, input_row):
        # Work around bug in DSS 3.1.0 API for single-column datasets
        if len(input_row) == 0 and len(self.input_schema) == 1:
            input_row = [u'']
        nb_cols = len(self.input_schema)
        output_row = Row(self.table_def)
        for col_no in range(nb_cols):
            col = self.input_schema[col_no]
            data = input_row[col_no]
            try:
                fieldSetterMap[col['type']](output_row, col_no, data)
            except Exception, e:
                self.errors += 1
                if self.errors < 100 or (self.errors < 10000 and self.errors % 100 == 0) or (self.errors % 1000 ==0):
                    print "[err #%s] Failed setting: col=%s type=%s val=%s  err=%s" % (self.errors, col["name"],  col["type"], data, e)
                raise
        self.table.insert(output_row)
        self.nrows += 1
        if self.nrows % 1000 == 0:
            print "TDE: Exported %d rows" % self.nrows


def upload_tde_file(tde_file, config):
    print "Start upload to Tableau server"
    ServerAPI.initialize()
    server_connection = ServerConnection()
    proxyUsername = config.get("proxy_username",'')
    proxyPassword = config.get("proxy_password",'')
    if proxyUsername != '':
        server_connection.setProxyCredentials(proxyUsername, proxyPassword)

    print "Connecting to server"
    server_connection.connect(
        config['server_url'],
        config['username'],
        config.get('password',''),
        config.get('site_id','') );

    project = config.get('project','default')
    if project == '':
        project = 'default'
    output_table = config.get('output_table','DSS_extract')
    if output_table == '':
        output_table = 'DSS_extract'

    print "Publishing extract"
    server_connection.publishExtract(
        tde_file,
        project,
        output_table,
        True ); # overwrite

    print "Disconnecting ..."
    server_connection.disconnect();
    server_connection.close();
    ServerAPI.cleanup();
    print "End upload to Tableau server"
