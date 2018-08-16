# -*- coding: utf-8 -*-
"""
@author: stijn_vanhoey
"""

import os
import csv
import yaml
from datetime import datetime
from collections import defaultdict, Mapping, Sequence
from pkg_resources import resource_filename

from dwca.read import DwCAReader
from cerberus import SchemaError
from jinja2 import FileSystemLoader, Environment

from pywhip.validators import DwcaValidator, WhipErrorHandler


def whip_dwca(dwca_zip, specifications, maxentries=None):
    """"""
    # Extract data header - only core support
    with DwCAReader(dwca_zip) as dwca:
        field_names = [field['term'].split('/')[-1] for field in
                       dwca.core_file.file_descriptor.fields]

    # Apply whip
    whip_it = Whip(specifications)
    whip_it._whip(whip_it.generate_dwca(dwca_zip),
                  field_names, maxentries)
    return whip_it


def whip_csv(csv_file, specifications, delimiter, maxentries=None):
    """"""

    # Extract data header
    with open(csv_file, "r") as dwc:
        reader = csv.DictReader(dwc, delimiter=delimiter)
        field_names = reader.fieldnames

    # Apply whip
    whip_it = Whip(specifications)
    whip_it._whip(whip_it.generate_csv(csv_file, delimiter),
                  field_names, maxentries)
    return whip_it


class Whip(object):

    def __init__(self, schema,
                 lowercase_terms=False):

        if not isinstance(schema, dict):
            raise SchemaError("Input schema need to be dictionary from "
                              "interpreted yaml file")

        if lowercase_terms:
            self.schema = self._decapitalize_schema(schema)
        else:
            self.schema = schema

        # setup a DwcaValidator instance
        self.validation = DwcaValidator(self.schema,
                                        error_handler=WhipErrorHandler)

        self.report = {'number_of_records': 0,
                       'executed_at': None,
                       'unvalidated_fields': None,  # exist in dataset, not in specs
                       'missing_fields': None,  # exist in specs, not in data set
                       'errors': {},
                       'warnings': []
                       }

        self._errors = {}

    @staticmethod
    def _decapitalize_schema(schema):
        """remove capitalize form"""
        lowercase_schema = {}
        for dwcterm, specification in schema.items():
            lowercase_schema[dwcterm.lower()] = specification
        return lowercase_schema

    def _conditional_fields(self, file_fields):
        """Extract the field names mentioned inside if conditions

        When fields are mentioned inside if statements, but not present in the
        data, this should raise a preliminar warning/message as part of the
        reporting
        """
        conditional_fields = []
        for _, specs in self.schema.items():
            if 'if' in specs.keys():
                if_rules = specs['if']
                # single if statement
                if isinstance(if_rules, Mapping):
                    conditional_fields += [key for key in if_rules.keys() if
                                          isinstance(if_rules[key], dict)]
                # multiple ifs combined
                elif isinstance(if_rules, Sequence):
                    for rule in if_rules:
                        conditional_fields += ([key for key in rule.keys() if
                                            isinstance(rule[key], dict)])
                else:
                    raise SchemaError
        if not set(conditional_fields).issubset(set(file_fields)):
            missing_if_fields = list(set(conditional_fields).difference(
                set(file_fields)))
            self.report['warnings'].append(
                'Following fields mentioned inside if specifications do not '
                'exist inside the document: {}'.format(
                    ', '.join(missing_if_fields)))

    def _compare_headers(self, file_fields):
        """Compare data fields and specifications

        Compare the fields mentioned by the specifications schema and the
        data set and update thereport attributes on unvalidated and missing
        fields

        Parameters
        ----------
        file_fields : list
            All fields present in the data-set.
        """
        try:
            file_fields = set(file_fields)
        except TypeError:
            raise TypeError

        self.report['unvalidated_fields'] = list(file_fields.difference(
            set(self.schema.keys())))
        self.report['missing_fields'] = list(set(self.schema.keys()).difference(
            file_fields))

    def _whip(self, input_generator, field_names, maxentries=None):
        """"""

        # preliminar checks
        self._compare_headers(field_names)
        self._conditional_fields(field_names)

        # validate each row and log the errors for each row
        for j, row in enumerate(input_generator):
            self.validation.validate(row)
            if len(self.validation._errors) > 0:
                row_id = j+1
                self._errors[row_id] = {}

                for error in self.validation._errors:
                    field = error.field
                    if field not in self._errors[row_id].keys():
                        self._errors[row_id][field] = []

                    if error.is_group_error:  # if/delimitedvalues
                        for child_error in error.child_errors:
                            error_info = dict()
                            error_info['value'] = child_error.value
                            error_info['rule'] = child_error.rule
                            error_info['constraint'] = str(child_error.constraint)
                            error_info['scope'] = error.rule
                            error_info['message'] = \
                                self.validation.schema.validator.error_handler._format_message(
                                    field, child_error)
                            self._errors[row_id][field].append(error_info)
                    else:
                        error_info = dict()
                        error_info['value'] = error.value
                        error_info['rule'] = error.rule
                        error_info['constraint'] = str(error.constraint)
                        error_info['scope'] = None
                        error_info['message'] = \
                            self.validation.schema.validator.error_handler._format_message(
                                field, error)
                        self._errors[row_id][field].append(error_info)

            if maxentries:
                if j >= maxentries-1:
                    break

        self.report['number_of_records'] = j + 1
        self.report['executed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M")

        self._errors_to_field_based()
        self._isitgreat()

    def _isitgreat(self):
        """check if there are any errors recorded"""
        if len(self._errors) == 0:
            print("Hooray, your data set is according to the guidelines!")
        else:
            print('Dataset does not comply the specifications, check errors'
                  ' for a more detailed information.')

    @staticmethod
    def generate_dwca(dwca_zip):
        """"""
        with DwCAReader(dwca_zip) as dwca:
            for row in dwca:
                document = {k.split('/')[-1]: v for k, v in row.data.items()}
                yield document

    @staticmethod
    def generate_csv(csv_file, delimiter):
        """"""
        with open(csv_file, "r") as dwc:
            reader = csv.DictReader(dwc, delimiter=delimiter)
            for document in reader:
                yield document

    def _errors_to_field_based(self):
        """Convert from line first to field first"""

        errorlog = defaultdict(lambda: defaultdict(
            lambda: defaultdict(list)))

        for ids, errordict in self._errors.items():
            for field, errors in errordict.items():
                for error in errors:
                    errorlog[field][error['rule']][ids].append(error)
        self.report["errors"] = errorlog

    @staticmethod
    def _get_list_items(value):
        """"""
        if isinstance(value, list):
            return value[0]
        else:
            return value

    def export_table(self, filename=None):
        """"""
        NotImplemented

        """
        errors_table = pd.DataFrame(self.errors).transpose()\
            .applymap(self._get_list_items)

        if len(errors_table) == 0:
            print("No report generated. No worries, your data set is "
                  "according to the guidelines!")
        if filename:
            errors_table.to_csv(filename)
        else:
            return errors_table
        """

    def percentage_correct(self):
        """get the percentage of correct values for each field"""
        error_enlist = defaultdict(list)

        for field, rules in self.report["errors"].items():
            for _, row_ids in rules.items():
                error_enlist[field] += (list(row_ids.keys()))

        # count unique
        total_records = self.report['number_of_records']
        correct_percentage = {key : 100*(1 - len(set(value))/total_records)
                            for (key, value) in error_enlist.items()}

        return correct_percentage

    def create_html(self, html_output="index.html"):
        """build html from report

        Parameters
        -----------
        html_output : str
            relative path and filename to write the resulting index.html
        """

        path = "./static/template.html"

        percentage = self.percentage_correct()

        html_template_path = resource_filename(__name__, path)
        env = Environment(loader=FileSystemLoader(
            os.path.dirname(html_template_path)))
        template = env.get_template(os.path.basename(html_template_path))
        html = template.render(report=self.report,
                               correct_percentage=percentage)

        with open(html_output, "w") as index_page:
            index_page.write(str(html))

