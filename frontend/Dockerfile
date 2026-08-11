FROM node:22-alpine

WORKDIR /frontend

COPY package.json package-lock.json ./
RUN npm ci

COPY . /frontend

EXPOSE 5173

CMD ["npm", "run", "dev"]
