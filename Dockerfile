FROM odoo:18.0

USER root
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --break-system-packages --ignore-installed --no-cache-dir -r /tmp/requirements.txt
USER odoo
