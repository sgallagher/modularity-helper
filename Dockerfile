FROM fedora-modularity/modularity-helper-deps

LABEL \
    name="Service to manage translations of Fedora Modules" \
    vendor="The Fedora Project" \
    license="MIT" \
    build-date=""

COPY modularity-helper.py .

USER 1001
EXPOSE 8080

CMD ["/usr/bin/gunicorn-3", "--bind", "0.0.0.0:8080", "--access-logfile", "-", "--enable-stdio-inheritance", "modularity-helper:application"]
