# 构建阶段:Node 打包 Vue → dist/
FROM node:20.18-alpine AS build
WORKDIR /app
# 先拷 package 利用层缓存:依赖没变就不重装
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# 运行阶段:Nginx 托管静态文件 + 反代 /api
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
