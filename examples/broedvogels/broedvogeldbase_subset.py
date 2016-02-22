# -*- coding: utf-8 -*-
"""
Created on Fri Feb  5 16:01:01 2016

@author: stijn_vanhoey
"""

from loganomalia import LogAnomaliaDWCA
from dwca.read import DwCAReader

#set up logging for row_id failures
logit = LogAnomaliaDWCA()

#with DwCAReader(os.path.join(ABS_PATH,
                        #'dwca-broedvogel-atlas-occurrences-v1.10.zip')) as dwca:

# de idee: iedereen kan zijn test maken door test-sequenties op te bouwen:
with DwCAReader('./broedvogel_corrupted_subset.zip') as dwca:
    for row in dwca:
        logit.check_equal(row, 'language', 'en')
        logit.check_equal(row, 'rightsHolder','INBO') #INTRO
        #logit.check_verbatimSRS(row)

print logit.log


