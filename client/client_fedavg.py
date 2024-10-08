# client_fedavg.py

import torch
import torch.optim as optim
from torch.utils.data import DataLoader
from utils.utils_fedavg import get_network
import logging

# Configure logging
logger = logging.getLogger(__name__)

class Client:
    def __init__(self, client_id, train_data, args):
        self.client_id = client_id
        self.train_loader = DataLoader(train_data, batch_size=args.batch_size, shuffle=True)
        self.args = args
        self.local_model = self.initialize_model()
        logger.info("Client %d initialized with model: %s", client_id, args.model)

    def initialize_model(self):
            im_size = (32, 32) if self.args.dataset == 'CIFAR10' or self.args.dataset == 'CelebA' else (28, 28)
            channel = 3 if self.args.dataset in ['CIFAR10', 'CelebA'] else 1
            num_classes = 10 if self.args.dataset != 'CelebA' else 2

            model = get_network(
                model=self.args.model,
                channel=channel,
                num_classes=num_classes,
                im_size=im_size
            ).to(self.args.device)
            
            logger.info("Global model initialized.")
            return model

    def set_model(self, global_model):
        self.local_model.load_state_dict(global_model)
        logger.info("Client %d set the global model.", self.client_id)

    def train(self):
        """Train the client's model on local data."""
        self.local_model.train()
        optimizer = optim.SGD(self.local_model.parameters(), lr=self.args.lr)
        criterion = torch.nn.CrossEntropyLoss()

        for epoch in range(self.args.local_epochs):
            for images, labels in self.train_loader:
                images, labels = images.to(self.args.device), labels.to(self.args.device)
                optimizer.zero_grad()
                outputs = self.local_model(images)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()

            logger.info("Client %d completed epoch %d with loss: %.4f", self.client_id, epoch + 1, loss.item())

        return self.local_model.state_dict()
