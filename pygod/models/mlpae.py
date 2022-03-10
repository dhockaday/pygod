# -*- coding: utf-8 -*-
""" Multilayer Perceptron Autoencoder
"""
# Author: Kay Liu <zliu234@uic.edu>
# License: BSD 2 clause

import torch
import torch.nn.functional as F
from torch_geometric.nn import MLP
from sklearn.metrics import roc_auc_score
from sklearn.utils.validation import check_is_fitted

from . import BaseDetector


class MLPAE(BaseDetector):
    """
    Vanila Multilayer Perceptron Autoencoder

    Parameters
    ----------
    hid_dim :  int, optional
        Hidden dimension of model. Defaults: ``0``.
    num_layers : int, optional
        Total number of layers in autoencoders. Defaults: ``4``.
    dropout : float, optional
        Dropout rate. Defaults: ``0.``.
    weight_decay : float, optional
        Weight decay (L2 penalty). Defaults: ``0.``.
    act : callable activation function or None, optional
        Activation function if not None.
        Defaults: ``torch.nn.functional.relu``.
    contamination : float, optional
        Valid in (0., 0.5). The proportion of outliers in the data set.
        Used when fitting to define the threshold on the decision
        function. Defaults: ``0.1``.
    lr : float, optional
        Learning rate. Defaults: ``0.004``.
    epoch : int, optional
        Maximum number of training epoch. Defaults: ``100``.
    gpu : int
        GPU Index, -1 for using CPU. Defaults: ``0``.
    verbose : bool
        Verbosity mode. Turn on to print out log information.
        Defaults: ``False``.

    Examples
    --------
    >>> from pygod.models import MLPAE
    >>> model = MLPAE()
    >>> model.fit(data)
    >>> prediction = model.predict(data)
    """
    def __init__(self,
                 hid_dim=64,
                 num_layers=4,
                 dropout=0.3,
                 weight_decay=0.,
                 act=F.relu,
                 contamination=0.1,
                 lr=5e-3,
                 epoch=100,
                 gpu=0,
                 verbose=False):
        super(MLPAE, self).__init__(contamination=contamination)

        # model param
        self.hid_dim = hid_dim
        self.num_layers = num_layers
        self.dropout = dropout
        self.weight_decay = weight_decay
        self.act = act

        # training param
        self.lr = lr
        self.epoch = epoch
        if gpu >= 0 and torch.cuda.is_available():
            self.device = 'cuda:{}'.format(gpu)
        else:
            self.device = 'cpu'

        # other param
        self.verbose = verbose
        self.model = None

    def fit(self, G):
        """
        Description
        -----------
        Fit detector with input data.

        Parameters
        ----------
        G : PyTorch Geometric Data instance (torch_geometric.data.Data)
            The input data.

        Returns
        -------
        self : object
            Fitted estimator.
        """
        x, labels = self.process_graph(G)

        channel_list = [x.shape[1]]
        for _ in range(self.num_layers-1):
            channel_list.append(self.hid_dim)
        channel_list.append(x.shape[1])
        relu_first = self.act is not None
        self.model = MLP(channel_list=channel_list,
                         dropout=self.dropout,
                         relu_first=relu_first,
                         batch_norm=False)

        # TODO: support channel specification after next pyg release
        # self.model = MLP(in_channels=x.shape[1],
        #                  hidden_channels=self.hid_dim,
        #                  out_channels=x.shape[1],
        #                  num_layers=self.num_layers,
        #                  dropout=self.dropout,
        #                  act=self.act)

        optimizer = torch.optim.Adam(self.model.parameters(),
                                     lr=self.lr,
                                     weight_decay=self.weight_decay)

        for epoch in range(self.epoch):
            self.model.train()
            x_ = self.model(x)
            loss = F.mse_loss(x_, x)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            score = torch.mean(F.mse_loss(x_, x, reduction='none')
                               , dim=1).detach().cpu().numpy()
            if self.verbose:
                # TODO: support more metrics
                auc = roc_auc_score(labels, score)
                print("Epoch {:04d}: Loss {:.4f} | AUC {:.4f}"
                      .format(epoch, loss.item(), auc))

        self.decision_scores_ = score
        self._process_decision_scores()
        return self

    def decision_function(self, G):
        """
        Description
        -----------
        Predict raw anomaly score using the fitted detector. Outliers
        are assigned with larger anomaly scores.

        Parameters
        ----------
        G : PyTorch Geometric Data instance (torch_geometric.data.Data)
            The input data.

        Returns
        -------
        outlier_scores : numpy.ndarray
            The anomaly score of shape :math:`N`.
        """
        check_is_fitted(self, ['model'])
        self.model.eval()

        x, _ = self.process_graph(G)
        x = x.to(self.device)

        x_ = self.model(x)
        outlier_scores = torch.mean(F.mse_loss(x_, x, reduction='none')
                                    , dim=1).detach().cpu().numpy()
        return outlier_scores

    def process_graph(self, G):
        """
        Description
        -----------
        Process the raw PyG data object into a tuple of sub data
        objects needed for the model.

        Parameters
        ----------
        G : PyTorch Geometric Data instance (torch_geometric.data.Data)
            The input data.

        Returns
        -------
        x : torch.Tensor
            Attribute (feature) of nodes.
        y : torch.Tensor
            Labels of nodes.
        """
        x = G.x.to(self.device)
        y = G.y
        return x, y
