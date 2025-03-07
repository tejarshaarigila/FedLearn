# ​Benchmarking **[Aggregation Free Federated Learning using Data Condensation](https://doi.org/10.48550/arXiv.2404.18962)** and Comparison with **[Federated Averaging](https://doi.org/10.48550/arXiv.1602.05629)**

  This project benchmarks Federated Learning Aggregation-Free (FedAF) (Wang et al., 2024) using the MNIST (Deng, 2012) and CIFAR-10 (Krizhevsky, 2009) datasets under non-independent and identically distributed (non-IID) data conditions with Federated Averaging (FedAvg) (McMahan et al., 2017).

## **FedAVG Implementation**

### **1. Parameters Overview**

#### **Model Parameters**
- **`model`**: Model architecture used for local training:
  - `'ConvNet'`: Convolutional Neural Network.
  - `'ResNet'`: Residual Network.
- **`device`**: Training device:
  - `'cuda'`: If GPU is available.
  - `'cpu'`: Otherwise.

#### **Training Parameters**
- **`local_epochs`**: Number of local training epochs per client.
- **`lr`**: Learning rate for the optimizer.
- **`batch_size`**: Batch size for local training.
- **`num_rounds`**: Total number of server-client communication rounds.

---

### **2. Default Configuration**

| **Parameter**      | **Default Value**    |
|---------------------|----------------------|
| `dataset`          | `'MNIST'`           |
| `model`            | `'ConvNet'`         |
| `device`           | `'cuda'` or `'cpu'` |
| `num_clients`      | `5`                 |
| `alpha`            | `0.1`               |
| `local_epochs`     | `10`                |
| `lr`               | `0.01`              |
| `batch_size`       | `64`                |
| `num_rounds`       | `20`                |

---

## **FedAF Implementation**

### **1. Parameters Overview**

#### **Training and Evaluation Parameters**
- **`Iteration`**: Local training steps per client.
- **`ipc`**: Instances per class for synthetic data condensation.
- **`lr_img`**: Learning rate for synthetic image optimization.
- **`steps`**: Frequency of global aggregation.
- **`temperature`**: Softmax temperature for logit aggregation.
- **`gamma`**: Momentum coefficient for logit aggregation.

---

### **2. Default Configuration**

| **Parameter**      | **Default Value**    |
|---------------------|----------------------|
| `dataset`          | `'MNIST'`           |
| `model`            | `'ConvNet'`         |
| `device`           | `'cuda'` or `'cpu'` |
| `num_partitions`   | `15`                |
| `alpha`            | `0.1`               |
| `Iteration`        | `1000`              |
| `ipc`              | `50`                |
| `lr_img`           | `1`                 |
| `steps`            | `500`               |
| `temperature`      | `2.0`               |
| `gamma`            | `0.9`               |
| `eval_mode`        | `'SS'`              |

---

## **Plotting Using `main_plot.py`**

### **1. Requirements**
- **Python Libraries**:
  - `torch`, `matplotlib`, `numpy`, `argparse`, `multiprocessing`, `torchvision`.
- **Model Checkpoints**:
  - Naming: `{method}_global_model_{round_number}.pth`.

---

### **2. Usage**

#### **Basic Command**
```bash
python main_plot.py --dataset CIFAR10 --model ConvNet --methods fedaf fedavg
```

#### **Command-Line Arguments**

| **Argument**         | **Type**  | **Default**    | **Description**                                                      |
|-----------------------|-----------|----------------|----------------------------------------------------------------------|
| `--dataset`          | `str`     | `CIFAR10`      | Dataset (`MNIST` or `CIFAR10`).                                      |
| `--model`            | `str`     | `ConvNet`      | Model architecture (e.g., `ConvNet`).                                |
| `--device`           | `str`     | Auto-detect    | Computation device (`cuda` or `cpu`).                                |
| `--test_repeats`     | `int`     | `5`            | Test repetition count for averaging.                                 |
| `--num_users`        | `int`     | `10`           | Number of clients/users.                                             |
| `--alpha_dirichlet`  | `float`   | `0.1`          | Dirichlet parameter for data heterogeneity.                          |
| `--methods`          | `list`    | `['fedaf', 'fedavg']` | Methods to compare.                                              |
| `--model_base_dir`   | `str`     | `/home/models` | Base directory for trained models.                                   |
| `--save_dir`         | `str`     | `/home/plots` | Directory to save plots.                                             |

---

### **3. Example Command**
```bash
python main_plot.py --dataset MNIST --model ConvNet --methods fedaf fedavg --num_users 10 --alpha_dirichlet 0.1
```

---
