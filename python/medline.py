from __future__ import division
import argparse
import datetime
import glob
import json
import os
import logging
import sys
import socket
import time
import traceback
import xml.parsers.expat
try:
    from lxml import etree as et
except ImportError:
    import xml.etree.cElementTree as et
from chemotext_util import Article
from chemotext_util import LoggingUtil
from chemotext_util import Medline
from chemotext_util import MedlineConf
from chemotext_util import MedlineQuant
from chemotext_util import SerializationUtil as SUtil
from chemotext_util import SparkUtil
from pyspark.sql import SQLContext

logger = LoggingUtil.init_logging (__file__)

def parse_line (xml_string):
    root = ET.fromstring(xml_string.encode('utf-8'))

def translate_record (rec, vocab):
    logger = LoggingUtil.init_logging (__file__)
    result = None
    pmid = rec.PMID ["#VALUE"]
    A, B, C = [], [], []
    date = SUtil.parse_month_year_date (rec.Article.Journal.JournalIssue.PubDate.Month,
                                        rec.Article.Journal.JournalIssue.PubDate.Year)
    if date:
        mesh_headings = rec.MeshHeadingList
        if mesh_headings:
            for mesh_heading in mesh_headings:
                for heading in mesh_heading:
                    descriptor_name = heading.DescriptorName
                    val = descriptor_name["#VALUE"].lower ()
                    if val in vocab.value['A']:
                        A.append (val)
                    elif val in vocab.value['B']:
                        B.append (val)
                    elif val in vocab.value['C']:
                        C.append (val)
            result = MedlineQuant ( pmid, date, A, B, C )
    return result

'''
Recreate original chemotext algorithm.
http://www.sciencedirect.com/science/article/pii/S1532046410000419
'''
def translate_record (rec, vocab):
    logger = LoggingUtil.init_logging (__file__)
    result = None
    pmid = rec.PMID ["#VALUE"]
    A, B, C = [], [], []
    date = SUtil.parse_month_year_date (rec.Article.Journal.JournalIssue.PubDate.Month,
                                        rec.Article.Journal.JournalIssue.PubDate.Year)
    if date:
        if rec.ChemicalList:
            for chems in rec.ChemicalList:
                for chem in chems:
                    A.append (chem.NameOfSubstance["#VALUE"])
        if rec.MeshHeadingList:
            for mesh_heading in rec.MeshHeadingList:
                for heading in mesh_heading:
                    descriptor_name = heading.DescriptorName
                    val = descriptor_name["#VALUE"].lower ()                    
                    major_topic = descriptor_name ["@MajorTopicYN"]
                    heading_ui = descriptor_name["@UI"]
                    if heading_ui.startswith ("D0"): # not in the paper
                        C.append (val)
                    if major_topic in [ 'Y', 'N' ]:
                        if heading.QualifierName:
                            qualifier_ui = None
                            if isinstance (heading.QualifierName, list):
                                for qualifier in heading.QualifierName:
                                    qualifier_ui = qualifier["@UI"]
                            else:
                                qualifier_ui = heading.QualifierName ["@UI"]
                            if qualifier_ui:
                                if qualifier_ui[0] in [ 'C', 'F' ]:
                                    C.append (val)
                                elif qualifier_ui.startswith ('Q'): # not in the paper
                                    B.append (val)
                                elif qualifier_ui.startswith ("D12"):
                                    B.append (val)
            print "A=> {0} \nB=> {1} \nC=> {2}".format (A, B, C)
            result = MedlineQuant ( pmid, date, A, B, C )
    return result

def make_triples (mquant):
    triples = []
    for a in mquant.A:
        for b in mquant.B:
            for c in mquant.C:
                triples.append ( [ a, b, c ] )
    return triples

def analyze_medline (conf):
    logger.info ("Conf: {0}".format (conf))
    sc = SparkUtil.get_spark_context (conf)
    Medline.data_root = conf.data_root    
    medline_conn = Medline (sc, conf, use_mem_cache=True)
    start = time.time()
    pmid_df = medline_conn.load_pmid_date_concurrent ()
    elapsed = time.time() - start
    logger.info ("Time elapsed:--> {0}".format (elapsed))

def main ():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host",  help="Mesos master host")
    parser.add_argument("--name",  help="Spark framework name")
    parser.add_argument("--data",  help="Chemotext data root.")    
    parser.add_argument("--venv",  help="Path to Python virtual environment to use")
    args = parser.parse_args()
    conf = MedlineConf (host           = args.host,
                        venv           = args.venv,
                        framework_name = args.name,
                        data_root      = args.data.replace ("file://", ""))
    analyze_medline (conf)

if __name__ == "__main__":
    main ()

