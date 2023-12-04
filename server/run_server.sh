if [ "$1" = "docker" ]; then
  sudo docker build -t server . && sudo docker run -p 8099:8099 -v "$(pwd)"/server_data:/app/server_data -v "$(pwd)"/db:/app/db --gpus=all -it server
else
  source server-env/bin/activate
  sudo ufw allow 8099
  python annotation_engine.py
fi;
