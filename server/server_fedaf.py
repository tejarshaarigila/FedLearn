# server_fedaf.py

import os
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
from torchvision import datasets, transforms
from utils.utils_fedaf import load_latest_model
import torch.optim as optim
import torchvision.transforms as transforms

def augment_data(images, augmentation_factor=2):
    """
    Applies data augmentation to the given set of images, considering their input dimensions.

    Args:
        images (torch.Tensor): The images to augment (shape: [N, C, H, W]).
        augmentation_factor (int): Number of times to augment each image.

    Returns:
        torch.Tensor: Augmented images.
    """
    _, _, height, width = images.shape  # Extract height and width from the input images

    transform = transforms.Compose([
        transforms.RandomCrop((height, width)), 
        transforms.RandomHorizontalFlip(), 
        transforms.RandomRotation(degrees=15),
        transforms.RandomAffine(degrees=0, translate=(0.1, 0.1)),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.1)
    ])
    
    augmented_images = []
    for _ in range(augmentation_factor):
        for img in images:
            augmented_img = transform(img.cpu()) 
            augmented_images.append(augmented_img)

    return torch.stack(augmented_images).to(images.device)

def ensure_directory_exists(path):
    """
    Ensures that the directory exists; if not, creates it.

    Args:
        path (str): Directory path to check and create.
    """
    if not os.path.exists(path):
        os.makedirs(path)

def dynamic_lambda_glob_client(r, total_rounds):
    """Dynamically adjusts lambda_glob at the client side based on the current round."""
    max_lambda = 1.0
    min_lambda = 0.5
    lambda_glob = min_lambda + (max_lambda - min_lambda) * (r / total_rounds)
    return lambda_glob

def train_model(model, train_loader, rc_tensor, num_classes, temperature, device, num_epochs):
    """
    Trains the model using the provided training data loader, including LGKM loss.

    Args:
        model (torch.nn.Module): The global model to train.
        train_loader (DataLoader): DataLoader for training data.
        rc_tensor (torch.Tensor): Aggregated class-wise soft labels from clients.
        num_classes (int): Number of classes.
        device (torch.device): Device to train on.
        num_epochs (int): Number of training epochs.
    """
    model.train()  # Set the model to training mode
    criterion_ce = nn.CrossEntropyLoss()  # Define the loss function
    optimizer = optim.SGD(model.parameters(), lr=0.001)  # Optimizer

    epsilon = 1e-6
    rc_smooth = rc_tensor + epsilon  # Smooth rc_tensor to avoid log(0)

    for epoch in range(num_epochs):

        running_loss = 0.0

        lambda_glob = dynamic_lambda_glob_client(epoch, num_epochs)

        # Compute T
        t_tensor = compute_T(model, train_loader.dataset, num_classes, temperature, device)
        
        valid_indices = [i for i in range(num_classes) if t_tensor[i] is not None]
        
        rc_tensor_filtered = torch.stack([rc_tensor[i] for i in valid_indices])
        t_tensor_filtered = torch.stack([t_tensor[i] for i in valid_indices])
        
        for inputs, labels in train_loader:
            inputs, labels = inputs.to(device), labels.to(device)

            optimizer.zero_grad()  # Zero the gradients at the start of each iteration

            outputs = model(inputs)
            loss_ce = criterion_ce(outputs, labels)  # Compute Cross-Entropy loss

            # Compute LGKM loss
            kl_div1 = nn.functional.kl_div(rc_tensor_filtered.log(), t_tensor_filtered, reduction='batchmean')
            kl_div2 = nn.functional.kl_div(t_tensor_filtered.log(), rc_tensor_filtered, reduction='batchmean')
            loss_lgkm = (kl_div1 + kl_div2) / 2

            # Combine the losses
            combined_loss = loss_ce + lambda_glob * loss_lgkm

            combined_loss.backward()  # Compute gradients
            optimizer.step()  # Update model parameters

            running_loss += loss_ce.item()

        print(f'Server: Epoch {epoch + 1}, Loss = CE Loss: {running_loss / len(train_loader):.4f} + Lambda: {lambda_glob} * LGKM Loss: {loss_lgkm.item():.4f} = {(running_loss / len(train_loader) + (lambda_glob * loss_lgkm.item())):.4f}')
        running_loss = 0.0

def evaluate_model(model, test_loader, device):
    """
    Evaluates the model's performance on the test dataset.

    Args:
        model (torch.nn.Module): The global model to evaluate.
        test_loader (DataLoader): DataLoader for test data.
        device (torch.device): Device to evaluate on.
    """
    model.eval()  # Set the model to evaluation mode
    total = 0
    correct = 0
    with torch.no_grad():  # No gradients needed
        for inputs, labels in test_loader:
            inputs, labels = inputs.to(device), labels.to(device)
            outputs = model(inputs)
            _, predicted = torch.max(outputs.data, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()

    accuracy = 100 * correct / total
    print(f'Accuracy of the network on test images: {accuracy:.2f}%')

def compute_T(model, synthetic_dataset, num_classes, temperature, device):
    """
    Computes the class-wise averaged soft labels T from the model's predictions on the synthetic data.
    """
    model.eval()
    class_logits_sum = [torch.zeros(num_classes, device=device) for _ in range(num_classes)]
    class_counts = [0 for _ in range(num_classes)]

    synthetic_loader = DataLoader(synthetic_dataset, batch_size=256, shuffle=False)

    with torch.no_grad():
        for inputs, labels in synthetic_loader:
            inputs, labels = inputs.to(device), labels.to(device)
            outputs = model(inputs)  # [batch_size, num_classes]
            for i in range(inputs.size(0)):
                label = labels[i].item()
                class_logits_sum[label] += outputs[i]
                class_counts[label] += 1

    t_list = []
    for c in range(num_classes):
        if class_counts[c] > 0:
            avg_logit = class_logits_sum[c] / class_counts[c]
            t_c = nn.functional.softmax(avg_logit / temperature, dim=0).mean(dim=0)
            t_list.append(t_c)
        else:
            # Initialize with uniform distribution if no data for class c
            t_list.append(None)

    t_tensor = torch.stack(t_list)  # [num_classes, num_classes]
    return t_tensor

def server_update(model_name, data, num_partitions, round_num, ipc, method, hratio, temperature, num_epochs, device="cuda" if torch.cuda.is_available() else "cpu"):
    """
    Aggregates synthetic data from all clients, updates the global model, evaluates it,
    and computes aggregated logits to send back to clients.

    Args:
        model_name (str): Model architecture (e.g., 'ConvNet').
        data (str): Dataset name ('CIFAR10' or 'MNIST').
        num_partitions (int): Number of client partitions.
        round_num (int): Current communication round number.
        ipc (int): Instances per class.
        method (str): Method used, e.g., 'fedaf'.
        hratio (float): Honesty ratio for client honesty.
        temperature (float): Temperature for softmax scaling.
        num_epochs (int): Number of epochs for training.
        device (str): Device to use for training ('cuda' or 'cpu').
    """
    # Define paths and ensure directories exist
    data_path = '/home/t914a431/data'
    model_dir = os.path.join('/home/t914a431/models', data, model_name, str(num_partitions), str(hratio))
    ensure_directory_exists(model_dir)

    # Load test dataset with necessary transformations
    if data == 'CIFAR10':
        channel = 3
        im_size = (32, 32)
        num_classes = 10
        mean = [0.4914, 0.4822, 0.4465]
        std = [0.2023, 0.1994, 0.2010]
        transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=mean, std=std)
        ])
        dst_test = datasets.CIFAR10(data_path, train=False, download=True, transform=transform)
    elif data == 'MNIST':
        channel = 1
        im_size = (28, 28)
        num_classes = 10
        mean = [0.1307]
        std = [0.3081]
        transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=mean, std=std)
        ])
        dst_test = datasets.MNIST(data_path, train=False, download=True, transform=transform)
    else:
        raise ValueError(f"Unsupported dataset: {data}")

    test_loader = DataLoader(dst_test, batch_size=256, shuffle=False)

    # Load aggregated class-wise soft labels Rc
    global_probs_path = os.path.join('logits', 'Global', f'Round{round_num}_Global_Rc.pt')
    if os.path.exists(global_probs_path):
        Rc = torch.load(global_probs_path, map_location=device)
        print("Server: Loaded aggregated class-wise soft labels R(c).")
    else:
        print("Server: No aggregated class-wise soft labels found.")
        Rc = [None for _ in range(num_classes)]

    all_images = []
    all_labels = []
    class_counts = torch.zeros(num_classes, device=device)
    
    # Aggregate synthetic data from all clients
    print("Server: Aggregating synthetic data from clients.")
    for client_id in range(num_partitions):
        synthetic_data_filename = os.path.join(
            'result',
            f'Client_{client_id}',
            f'res_{method}_{data}_{model_name}_Client{client_id}_{ipc}ipc_Round{round_num}.pt'
        )
    
        if os.path.exists(synthetic_data_filename):
            try:
                data_dict = torch.load(synthetic_data_filename, map_location=device)
                if 'images' in data_dict and 'labels' in data_dict and data_dict['images'].size(0) > 0:
                    print(f"Server: Loaded synthetic data from Client {client_id}.")
                    images, labels = data_dict['images'], data_dict['labels']
                    all_images.append(images)
                    all_labels.append(labels)
    
                    # Update class counts
                    for label in labels:
                        class_counts[label] += 1
                else:
                    print(f"Server: No valid synthetic data from Client {client_id}. Skipping.")
            except Exception as e:
                print(f"Server: Error loading data from Client {client_id} - {e}")
        else:
            print(f"Server: No synthetic data found for Client {client_id} at {synthetic_data_filename}. Skipping.")
    
    if not all_images:
        print("Server: No synthetic data aggregated from clients. Skipping model update.")
        # Initialize aggregated logits with zeros
        aggregated_logits = [None for _ in range(num_classes)]
        return aggregated_logits
    
    # Concatenate all synthetic data
    all_images = torch.cat(all_images, dim=0)
    all_labels = torch.cat(all_labels, dim=0)
    
    # Handle class imbalance by augmenting underrepresented classes
    max_class_count = class_counts.max()
    balanced_images = []
    balanced_labels = []
    
    for c in range(num_classes):
        class_indices = (all_labels == c).nonzero(as_tuple=True)[0]
        class_images = all_images[class_indices]
        class_labels = all_labels[class_indices]
    
        if class_indices.numel() < max_class_count:
            # Perform data augmentation to match max_class_count
            augmentation_factor = (max_class_count // class_indices.numel()) - 1
            augmented_images = augment_data(class_images, augmentation_factor=augmentation_factor)
            augmented_labels = torch.full((augmented_images.size(0),), c, device=device, dtype=torch.long)
    
            class_images = torch.cat([class_images, augmented_images], dim=0)
            class_labels = torch.cat([class_labels, augmented_labels], dim=0)
    
        balanced_images.append(class_images)
        balanced_labels.append(class_labels)
    
    balanced_images = torch.cat(balanced_images, dim=0)
    balanced_labels = torch.cat(balanced_labels, dim=0)
    
    print(f"Server: Class counts after augmentation: {[balanced_labels.tolist().count(i) for i in range(num_classes)]}")
    
    # Create training dataset and loader
    final_dataset = TensorDataset(balanced_images, balanced_labels)
    train_loader = DataLoader(final_dataset, batch_size=256, shuffle=True)

    # Load the latest global model
    print("Server: Loading the latest global model.")
    net = load_latest_model(model_dir, model_name, channel, num_classes, im_size, device)
    net.train()

    rc_tensor_valid = [r for r in Rc if r is not None]
    if rc_tensor_valid:
        rc_tensor = torch.stack(rc_tensor_valid).to(device)  # Use only valid logits
    else:
        print("Server: No valid Rc tensors available, skipping this round.")
        return

    # Train the global model
    print("Server: Starting global model training.")
    train_model(net, train_loader, rc_tensor, num_classes, temperature, device, num_epochs=num_epochs)

    # Evaluate the updated global model
    print("Server: Evaluating the updated global model.")
    evaluate_model(net, test_loader, device)

    # Save the updated global model
    model_path = os.path.join(model_dir, f"fedaf_global_model_{round_num}.pth")
    try:
        ensure_directory_exists(os.path.dirname(model_path))
        torch.save(net.state_dict(), model_path)
        print(f"Server: Global model updated and saved to {model_path}.")
    except Exception as e:
        print(f"Server: Error saving the global model - {e}")
