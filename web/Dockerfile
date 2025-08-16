# ---- deps ----
FROM node:20-alpine AS deps
WORKDIR /app

# Install prod+dev deps (for build) using npm lockfile if present
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# ---- build ----
FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Build Next (app router)
RUN npm run build

# ---- run ----
FROM node:20-alpine AS run
WORKDIR /app
ENV NODE_ENV=production

# Copy only what the runtime needs
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY package.json package-lock.json* ./

# Install only production deps
RUN if [ -f package-lock.json ]; then npm ci --omit=dev; else npm install --omit=dev; fi

EXPOSE 3000
CMD ["npm", "start", "--", "-p", "3000"]
