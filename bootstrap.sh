#!/bin/sh

# scribe-next modification: stop on generation errors and preserve argument boundaries.
set -e

# To be safe include -I flag
autoreconf --force --verbose --install
./configure --config-cache "$@"
