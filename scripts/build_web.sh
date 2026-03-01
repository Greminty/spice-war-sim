#!/bin/bash
set -e

cd "$(dirname "$0")/.."

mkdir -p web/python

cd src
zip -r ../web/python/spice_war.zip spice_war/ -x "spice_war/__pycache__/*" "spice_war/**/__pycache__/*"
cd ..

echo "Built web/python/spice_war.zip"
