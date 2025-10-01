
## Building and Running the Docker Container

Follow these steps to build and run the application using Docker:

### 1. Build the Docker Image

```bash
docker build -t app .
```

This command builds the Docker image from the current directory and tags it as `app`.

### 2. Run the Docker Container

```bash
docker run -p 8080:80 app
```

This command runs the container, mapping port `8080` on your host to port `80` in the container.

### Accessing the Application

Once the container is running, open your browser and navigate to:

```
http://localhost:8080
```

to access the application.

## Deploy ECS

1. Retrieve an authentication token and authenticate your Docker client to your registry. Use the AWS CLI:

```bash
aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin 637423235030.dkr.ecr.us-east-2.amazonaws.com
```

2.  Build your Docker image using the following command. For information on building a Docker file from scratch see the instructions here . You can skip this step if your image is already built:
```bash
docker build -t app .

docker buildx build --platform linux/amd64 -t app .

```

3. After the build completes, tag your image so you can push the image to this repository:
```bash
docker tag app:latest 637423235030.dkr.ecr.us-east-2.amazonaws.com/app:latest
```

4. Run the following command to push this image to your newly created AWS repository:
```bash
docker push 637423235030.dkr.ecr.us-east-2.amazonaws.com/app:latest
```