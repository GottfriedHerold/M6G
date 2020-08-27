# Intended to be run as command "source coverage_report.sh" from the current virtual environment rather than in a sub-shell, hence no chmod +x
coverage run --source='.' runtests.py
coverage html
