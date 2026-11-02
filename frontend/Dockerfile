FROM node:22-bookworm-slim AS build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
COPY VERSION ./VERSION
ARG APP_COMMIT=unknown
RUN npm run build
RUN node -e 'const fs = require("node:fs"); fs.writeFileSync("dist/frontend-version.json", JSON.stringify({version: fs.readFileSync("VERSION", "utf8").trim(), commit: process.env.APP_COMMIT}));'

FROM nginx:stable-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /frontend/dist/ /usr/share/nginx/html/
ARG APP_COMMIT=unknown
LABEL org.opencontainers.image.revision="${APP_COMMIT}"
EXPOSE 80
