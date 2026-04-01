# This file is to circumvent issues with Windows binding volumes as directories instead of files.
# https://gist.github.com/onjin/2dd3cc52ef79069de1faa2dfd456c945?permalink_comment_id=3233077#gistcomment-3233077
FROM postgres:16-alpine
COPY init.sql /docker-entrypoint-initdb.d/init.sql
RUN chmod 644 /docker-entrypoint-initdb.d/init.sql
