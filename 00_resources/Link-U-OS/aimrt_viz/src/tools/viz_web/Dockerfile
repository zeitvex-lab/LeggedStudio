FROM nginx:latest

# 移除默认配置
RUN rm /etc/nginx/conf.d/default.conf

# 复制nginx配置
ADD nginx.conf /etc/nginx/conf.d/default.conf

# 复制静态文件
COPY dist /usr/share/nginx/html/cloud
