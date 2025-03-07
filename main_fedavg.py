import torch
from server.server_fedavg import Server
from client.client_fedavg import Client
from utils.utils_fedavg import load_data, randomize_labels, load_client_data
import logging
import random
import numpy as np
from concurrent.futures import ProcessPoolExecutor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ARGS:
    def __init__(self):
        self.dataset = 'MNIST'  # 'MNIST' - 'CIFAR10' - 'CelebA'
        self.model = 'ConvNet'  # 'ConvNet' - 'ResNet'
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.num_clients = 5
        self.alpha = 0.1  # Dirichlet distribution parameter
        self.local_epochs = 10
        self.lr = 0.01
        self.batch_size = 64
        self.num_rounds = 20
        self.honesty_ratio = 1  # Ratio of Honest Clients

        if self.dataset == 'MNIST':
            self.channel = 1
            self.num_classes = 10
            self.im_size = (28, 28)
        elif self.dataset == 'CIFAR10':
            self.channel = 3
            self.num_classes = 10
            self.im_size = (32, 32)
        elif self.dataset == 'CelebA':
            self.channel = 3
            self.num_classes = 2
            self.im_size = (64, 64)

def train_client(client_state):
    client_id, args_state, global_model_state, is_dishonest = client_state
    # Reconstruct ARGS object
    args = ARGS()
    args.__dict__.update(args_state)
    # Load client's data
    train_data = load_client_data(client_id, args)
    # Apply label randomization if the client is dishonest
    if is_dishonest:
        train_data = randomize_labels(train_data)
    # Reconstruct Client
    client = Client(client_id=client_id, train_data=train_data, args=args)
    client.set_model(global_model_state)
    return client.train()

def main():
    args = ARGS()
    # Set random seeds for reproducibility
    random.seed(42)
    np.random.seed(42)
    torch.manual_seed(42)

    logger.info("Starting Federated Learning with %d clients", args.num_clients)

    # Load data and distribute to clients
    full_train_dataset, client_indices, test_loader = load_data(dataset=args.dataset, alpha=args.alpha, num_clients=args.num_clients)
    logger.info("Data loaded and distributed to clients.")

    # Initialize server
    server = Server(args)

    # Determine which clients are honest and which are dishonest
    num_honest_clients = int(args.honesty_ratio * args.num_clients)
    honest_clients = random.sample(range(args.num_clients), num_honest_clients)

    data_sizes = []  # Collect data sizes of clients

    # Collect data sizes for weighting during aggregation
    for i in range(args.num_clients):
        indices = client_indices[i]
        data_size = len(indices)
        data_sizes.append(data_size)

    # Lists to collect test accuracies
    test_accuracies = []

    # Federated learning rounds
    for round_num in range(1, args.num_rounds + 1):
        logger.info("\n--- Round %d ---", round_num)

        # Distribute global model to clients
        global_model = server.get_global_model()

        # Prepare client states for parallel execution
        client_states = []
        for client_id in range(args.num_clients):
            is_dishonest = client_id not in honest_clients
            client_state = (
                client_id,
                vars(args),
                global_model,  # Global model state_dict
                is_dishonest
            )
            client_states.append(client_state)

        # Clients perform local training in parallel
        with ProcessPoolExecutor() as executor:
            client_models = list(executor.map(train_client, client_states))

        # Server aggregates client models using data sizes
        server.aggregate(client_models, data_sizes)

        # Evaluate global model on test data
        accuracy = server.evaluate(test_loader, round_num)
        test_accuracies.append(accuracy)

    logger.info("Federated Learning completed.")

if __name__ == "__main__":
    main()
