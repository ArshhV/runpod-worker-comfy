#!/bin/bash

# update_docker_image.sh
# Script to update Docker image without rebuilding everything from scratch

# Configuration
BASE_IMAGE="araiv4/runpod-worker-comfy:wan"
NEW_TAG="araiv4/runpod-worker-comfy:wan-$(date +%Y%m%d)"
PLATFORM="linux/amd64"

# Print colorful messages
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Docker Image Update Script${NC}"
echo "This script will create an updated version of your Docker image without rebuilding everything."
echo "Base image: $BASE_IMAGE"
echo "New image tag: $NEW_TAG"

# Check if Dockerfile.update exists and back it up if it does
if [ -f "Dockerfile.update" ]; then
    echo "Backing up existing Dockerfile.update to Dockerfile.update.bak"
    cp Dockerfile.update Dockerfile.update.bak
fi

# Create temporary Dockerfile.update
echo "FROM $BASE_IMAGE" > Dockerfile.update

# Ask user for changes
echo -e "\n${YELLOW}Enter your Dockerfile changes below (e.g., RUN pip install package).${NC}"
echo "Type 'done' on a new line when finished:"

while true; do
    read -r line
    if [ "$line" = "done" ]; then
        break
    fi
    echo "$line" >> Dockerfile.update
done

# Show the created Dockerfile.update
echo -e "\n${YELLOW}Created Dockerfile.update:${NC}"
cat Dockerfile.update

# Confirm before building
echo -e "\n${YELLOW}Ready to build updated image.${NC}"
read -p "Continue? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo "Build cancelled."
    exit 1
fi

# Build the updated image
echo -e "\n${YELLOW}Building updated Docker image...${NC}"
docker build --platform $PLATFORM -t $NEW_TAG -f Dockerfile.update .

# Check if build was successful
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}Successfully built updated image: $NEW_TAG${NC}"
    
    # Ask if user wants to tag as latest
    read -p "Do you want to tag this as 'latest' as well? (y/n): " tag_latest
    if [ "$tag_latest" = "y" ]; then
        docker tag $NEW_TAG "${BASE_IMAGE%:*}:latest"
        echo "Tagged as ${BASE_IMAGE%:*}:latest"
    fi
    
    # Ask if user wants to push the image
    read -p "Do you want to push this image to the registry? (y/n): " push_image
    if [ "$push_image" = "y" ]; then
        echo "Pushing image to registry..."
        docker push $NEW_TAG
        if [ "$tag_latest" = "y" ]; then
            docker push "${BASE_IMAGE%:*}:latest"
        fi
        echo -e "${GREEN}Image pushed to registry${NC}"
    fi
else
    echo -e "\n${YELLOW}Build failed.${NC}"
    exit 1
fi

echo -e "\n${GREEN}Update process completed.${NC}"