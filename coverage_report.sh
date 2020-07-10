# Intended to be run with source coverage_report.sh from the current environment rather than in a sub-shell, hence no chmod +x
coverage run --source='.' runtests.py
coverage html
