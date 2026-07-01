FROM nginx:alpine

# Copy static dashboard page
COPY index.html /usr/share/nginx/html/index.html

# Copy Nginx template for dynamic reverse proxy substitution
COPY default.conf.template /etc/nginx/templates/default.conf.template

# Default fallback environment variable to prevent Nginx startup syntax errors
ENV PICO_UPS_URL=http://127.0.0.1:9999

# Expose port 80
EXPOSE 80
