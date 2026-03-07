import os

PROJECTS_DIR = os.environ.get('BP_PROJECTS_DIR', '/srv/bookpublisher/projects')
GLOBAL_DIR   = os.environ.get('BP_GLOBAL_DIR',   '/srv/bookpublisher/global')
BUILDS_DIR   = os.environ.get('BP_BUILDS_DIR',   '/srv/bookpublisher/builds')
