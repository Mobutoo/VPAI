FROM pandoc/core:3.6
RUN apk add --no-cache nodejs npm
WORKDIR /app
COPY package.json .
RUN npm install --production
COPY server.js .
COPY reference/ ./reference/
ENTRYPOINT []
CMD ["node", "server.js"]
