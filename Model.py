import torch
import torch.nn as nn

import Module as at_module

class FNblock(nn.Module):
    """ 
    """
    def __init__(self, input_size, hidden_size=256, dropout=0.2, is_online=False, is_first=False):
        """the block of full-band and narrow-band fusion
        """
        super(FNblock, self).__init__()
        self.input_size = input_size
        self.full_hidden_size =  hidden_size // 2
        self.is_first = is_first
        self.is_online = is_online
        if self.is_online:
            self.narr_hidden_size = hidden_size
        else:
            self.narr_hidden_size = hidden_size  // 2
        self.dropout = dropout

        self.dropout_full =  nn.Dropout(p=self.dropout)
        self.dropout_narr = nn.Dropout(p=self.dropout)
        ### LSTM input (batch_size, sequence_length, input_size)
        ### LSTM output (batch_size, sequence_length, D*H_out) 
        ## x_in: torch.Size([596, 256, 4]) 
        ## x_out: torch.Size([596, 256, 2*128]) [full_hidden_size=256/2=128=hidden_out_size]
        self.fullLstm = nn.LSTM(input_size=self.input_size, hidden_size=self.full_hidden_size, batch_first=True, bidirectional=True)
        if self.is_first:
              ## x_in: torch.Size([512, 298, 260])
              ## x_out: torch.Size([512, 298, 2*128]) [narr_hidden_size=256/2=128=hidden_out_size]
              self.narrLstm = nn.LSTM(input_size=2*self.full_hidden_size+self.input_size, hidden_size=self.narr_hidden_size, batch_first=True, bidirectional=not self.is_online)
        else:
            self.narrLstm = nn.LSTM(input_size=2*self.full_hidden_size, hidden_size=self.narr_hidden_size, batch_first=True, bidirectional=not self.is_online)
        
    def forward(self, x, nb_skip=None, fb_skip=None):
        ## nb:2/nt:298/nf:256/nc:4
        nb,nt,nf,nc = x.shape
        ## (permute) nb:2/nf:256/nt:298/nc:4
        ## nb_skip1: torch.Size([512, 298, 4])
        ## nb_skip2: torch.Size([512, 298, 256])
        ## nb_skip3: torch.Size([512, 298, 256])
        nb_skip = x.permute(0,2,1,3).reshape(nb*nf,nt,-1)
        ## x1: torch.Size([596, 256, 4]) 
        ## x2: torch.Size([596, 256, 256])
        ## x3: torch.Size([596, 256, 256]) 
        x = x.reshape(nb*nt,nf,-1)
        if not self.is_first:
            x = x + fb_skip
        x, _ = self.fullLstm(x)
        ## x: torch.Size([596, 256, 256])
        fb_skip = x
        x = self.dropout_full(x)
        ## (view) nb:2/nt:298/nf:256/256 (permute) nb:2/nf:256/nt:298/256 (reshape) torch.Size([512, 298, 256])
        x = x.view(nb,nt,nf,-1).permute(0,2,1,3).reshape(nb*nf,nt,-1)
        if self.is_first:  
            ## x: torch.Size([512, 298, 260])
            x = torch.cat((x,nb_skip),dim=-1)
        else:
            x = x + nb_skip
        x, _ = self.narrLstm(x)
        ## x, nb_skip: torch.Size([512, 298, 256])
        nb_skip = x
        x = self.dropout_narr(x)
        ## (view) nb:2/nf:256/nt:298/256 (permute) nb:2/nt:298/nf:256/256
        x = x.view(nb,nf,nt,-1).permute(0,2,1,3)
        ## torch.Size([2, 298, 256, 256]) torch.Size([596, 256, 256]) torch.Size([512, 298, 256])
        return x, fb_skip, nb_skip

       
class FN_SSL(nn.Module):
    """ 
    """
    def __init__(self,input_size=4,hidden_size=256,is_online=True,is_doa=False):
        """the block of full-band and narrow-band fusion
        """
        super(FN_SSL, self).__init__()
        self.is_online = is_online
        self.is_doa = is_doa
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.block_1 = FNblock(input_size=self.input_size,is_online=self.is_online, is_first=True)
        # self.block_2 = FNblock(input_size=self.hidden_size,is_online=self.is_online, is_first=False)
        # self.block_3 = FNblock(input_size=self.hidden_size,is_online=self.is_online, is_first=False)        
        self.emb2ipd = nn.Linear(256,2)
        self.pooling = nn.AvgPool2d(kernel_size=(12, 1))
        self.tanh = nn.Tanh()
        if self.is_doa:
            self.ipd2doa = nn.Linear(512,180)
    def forward(self,x):
        ## nb:2/nc:4/nf:256/nt:298
        ## nb:2/nt:298/nf:256/nc:4
        x = x.permute(0,3,2,1)
        nb,nt,nf,nc = x.shape
        x, fb_skip, nb_skip = self.block_1(x)
        # x, fb_skip, nb_skip = self.block_2(x,fb_skip=fb_skip, nb_skip=nb_skip)
        # x, fb_skip, nb_skip = self.block_3(x,fb_skip=fb_skip, nb_skip=nb_skip)  
        x = x.permute(0,2,1,3).reshape(nb*nf,nt,-1)   
        ipd = self.pooling(x)
        ipd = self.tanh(self.emb2ipd(ipd))
        _, nt2, _ = ipd.shape
        ipd = ipd.view(nb,nf,nt2,-1)
        ipd = ipd.permute(0,2,1,3)
        ipd_real = ipd[:,:,:,0]
        ipd_image = ipd[:,:,:,1]
        result = torch.cat((ipd_real,ipd_image),dim=2)
        if self.is_doa:
            result = self.ipd2doa(result)
        return result

# class FN_lightning(nn.Module):
#     def __init__(self):
#         """the block of full-band and narrow-band fusion
#         """
#         super(FN_lightning, self).__init__()
#         self.arch = FN_SSL()
#     def forward(self,x):
#         return self.arch(x)
    

if __name__ == "__main__":
	import torch
    ## input: nb:2/nc:4/nf:256/nt:298
	input = torch.randn((2,4,256,298)).cuda()
	net = FN_SSL().cuda()
	ouput = net(input)
    # output: torch.Size([2, 24, 512])
	print(ouput.shape)
	print('# parameters:', sum(param.numel() for param in net.parameters()))
