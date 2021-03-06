# -*- coding: utf-8 -*-
import os, sys

# env
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "djpsilobus.settings")

from django.conf import settings

from djpsilobus.core.dspace import Search

import argparse
import requests

# set up command-line options
desc = """
Accepts as input an optional collection name.
Returns collection or all collections if no name provided.
"""

parser = argparse.ArgumentParser(description=desc)

parser.add_argument(
    "-n", "--name",
    required=True,
    help="The name of the collection",
    dest="name"
)

def main():
    """
    Using the DSpace REST API, retrieve a collection by name
    """

    s = Search()

    jason = s.collection(name)

    print(jason)

######################
# shell command line
######################

if __name__ == "__main__":
    args = parser.parse_args()
    name = args.name

    sys.exit(main())
