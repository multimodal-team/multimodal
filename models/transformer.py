import torch
import torch.nn as nn

import numpy as np


class PositionwiseFeedForward(nn.Module):
    """docstring for PositionwiseFeedForward"""

    def __init__(self, d_in, d_hid, dropout=0.1):
        super(PositionwiseFeedForward, self).__init__()
        self.w1 = nn.Linear(d_in, d_hid)
        self.w2 = nn.Linear(d_hid, d_in)
        self.relu = nn.ReLU()

    def forward(self, x):
        output = self.w2(self.relu(self.w1(x)))
        return output


class ScaleDotProductAttention(nn.Module):
    """docstring for ScaleDotProductAttention"""

    def __init__(self, dropout=0.0):
        super(ScaleDotProductAttention, self).__init__()
        self.softmax = nn.Softmax(dim=-1)
        self.dropout = nn.Dropout(dropout)

    def forward(self, q, k, v, mask=None):
        """
        q, k, v: [batch_size, file_size, word_embedding_size]
        mask: batch x q_len x v_len
        """
        dk = q.shape[2]
        attention = torch.bmm(q, k.transpose(1, 2)) / np.sqrt(dk)  # [b, n, m]*[b, m, n] batch matrix-matrix product
        if mask:    
            attention = attention + mask
        attention = self.softmax(attention)
        attention = self.dropout(attention)
        context = torch.bmm(attention, v)
        return context, attention


class MultiHeadAttention(nn.Module):
    def __init__(self, model_dim=768, num_heads=8, dropout=0.1):
        super(MultiHeadAttention, self).__init__()
        self.d = model_dim // num_heads
        self.num_head = num_heads
        # [batch_size, file_size, self.num_head*self.d]
        self.linear_k = nn.Linear(model_dim, self.num_head * self.d)
        self.linear_q = nn.Linear(model_dim, self.num_head * self.d)
        self.linear_v = nn.Linear(model_dim, self.num_head * self.d)

        self.dotAttention = ScaleDotProductAttention(dropout)

    def forward(self, key, value, query, mask=None):
        d = self.d
        num_head = self.num_head
        batch_size = key.shape[0]
        # linear projection
        k = self.linear_k(key)
        q = self.linear_q(query)
        v = self.linear_v(value)

        # tensor transform
        k = k.view(batch_size * num_head, -1, d)
        q = q.view(batch_size * num_head, -1, d)
        v = v.view(batch_size * num_head, -1, d)

        # self attention
        context, attention = self.dotAttention(q, k, v, mask)
        output = context.view(batch_size, -1, num_head * d)

        return output, attention


class EncoderLayer(nn.Module):
    def __init__(self, model_dim=768, num_heads=8, ffw_dim=2048, dropout=0.1):
        super(EncoderLayer, self).__init__()
        self.Attention = MultiHeadAttention(model_dim, num_heads, dropout)
        self.LN1 = nn.LayerNorm(model_dim)
        self.dropout1 = nn.Dropout(dropout)
        self.Feed_forward = PositionwiseFeedForward(model_dim, ffw_dim, dropout)
        self.LN2 = nn.LayerNorm(model_dim)
        self.dropout2 = nn.Dropout(dropout)

    def forward(self, x, attn_mask=None):
        context, attention = self.Attention(x, x, x, attn_mask)
        x = self.LN1(x + self.dropout1(context))
        output = self.Feed_forward(x)
        output = self.LN2(x + self.dropout2(output))
        return output, attention


class Encoder(nn.Module):
    def __init__(self, num_layers, model_dim, num_heads, ffw_dim, dropout):
        super(Encoder, self).__init__()
        self.encoder_layers = nn.ModuleList([EncoderLayer(model_dim, num_heads, ffw_dim, dropout) 
                                            for _ in range(num_layers)])

    def forward(self, x, attn_mask=None):
        """
        mask: batch x v_len, 1 for real positions that are attended to, 0 for padded positions
        """
        if attn_mask:
            attn_mask = attn_mask.unsqueeze(1)    # batch x q_len x v_len
            attn_mask = (1.0 - attn_mask) * -10000.0

        attentions = ()
        for enc in self.encoder_layers:
            x, attention = enc(x, attn_mask)
            attentions = attentions + (attention, )
        return x, attentions