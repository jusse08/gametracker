# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build application
RUN npm run build

# Production stage
FROM node:20-alpine

WORKDIR /app

# Copy built files
COPY --from=builder /app/dist ./dist

# Install serve to serve static files
RUN npm install -g serve

# Expose port
EXPOSE 3000

# Start server
CMD ["serve", "-s", "dist", "-l", "3000"]
