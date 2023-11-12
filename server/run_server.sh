sudo docker build -t server . && sudo docker run -p 8099:8099 -v "$(pwd)"/server_data:/app/server_data -v "$(pwd)"/db:/app/db --gpus=all -it server
