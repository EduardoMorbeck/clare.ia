# syntax=docker/dockerfile:1

# --- Estágio base: dependências instaladas (compartilhado por dev e build) ---
FROM node:22-alpine AS deps
WORKDIR /app
# Instala dependências a partir do lockfile (camada cacheada até o lock mudar).
COPY package.json package-lock.json ./
RUN npm ci

# --- Estágio dev: Vite dev server com hot-reload (usado pelo compose.override) ---
FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# --- Estágio build: gera os assets estáticos de produção em /app/dist ---
FROM deps AS build
COPY . .
RUN npm run build

# --- Estágio 2: servir o estático com Nginx (imagem final enxuta) ---
FROM nginx:1.27-alpine AS runtime

# Config que serve a SPA e faz proxy de /api para o backend.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Apenas os arquivos buildados entram na imagem final (sem node_modules).
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
