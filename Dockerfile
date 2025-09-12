FROM ankane/pgvector

COPY init_tables.sh /docker-entrypoint-initdb.d/init_tables.sh
RUN chmod +x /docker-entrypoint-initdb.d/init_tables.sh
