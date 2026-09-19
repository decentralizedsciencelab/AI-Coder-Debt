import React, { createContext, useContext, useState, useEffect } from 'react';
import { ethers } from 'ethers';

// Create context
const Web3Context = createContext();

// Contract ABI
const contractABI = []; // Replace with actual ABI

// Contract addresses for different networks
const CONTRACT_ADDRESSES = {
  1: '0x...', // Ethereum Mainnet
  11155111: '0x...', // Sepolia Testnet
  // Add more networks as needed
};

export function Web3Provider({ children }) {
  const [account, setAccount] = useState(null);
  const [provider, setProvider] = useState(null);
  const [signer, setSigner] = useState(null);
  const [contract, setContract] = useState(null);
  const [networkId, setNetworkId] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);

  // Initialize provider
  useEffect(() => {
    const initProvider = async () => {
      try {
        if (window.ethereum) {
          const provider = new ethers.BrowserProvider(window.ethereum);
          setProvider(provider);
          
          // Get network
          const network = await provider.getNetwork();
          setNetworkId(network.chainId);
          
          // Listen for network changes
          window.ethereum.on('chainChanged', (chainId) => {
            window.location.reload();
          });
        } else {
          setError('Please install MetaMask or another Ethereum wallet');
        }
      } catch (error) {
        console.error('Error initializing provider:', error);
        setError('Error connecting to blockchain');
      }
    };

    initProvider();
  }, []);

  // Connect wallet
  const connectWallet = async () => {
    try {
      if (!provider) {
        throw new Error('Provider not initialized');
      }
      
      // Request account access
      const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
      const account = accounts[0];
      setAccount(account);
      
      // Get signer
      const signer = await provider.getSigner();
      setSigner(signer);
      
      // Initialize contract
      const contractAddress = CONTRACT_ADDRESSES[networkId];
      if (contractAddress) {
        const contract = new ethers.Contract(contractAddress, contractABI, signer);
        setContract(contract);
      } else {
        setError('Contract not deployed on this network');
      }
      
      setIsConnected(true);
    } catch (error) {
      console.error('Error connecting wallet:', error);
      setError('Error connecting wallet');
    }
  };

  // Disconnect wallet
  const disconnectWallet = () => {
    setAccount(null);
    setSigner(null);
    setContract(null);
    setIsConnected(false);
  };

  // Read from contract
  const readContract = async (method, args = []) => {
    try {
      if (!contract) {
        throw new Error('Contract not initialized');
      }
      
      return await contract[method](...args);
    } catch (error) {
      console.error(`Error calling ${method}:`, error);
      setError(`Error calling ${method}`);
      return null;
    }
  };

  // Write to contract
  const writeContract = async (method, args = [], options = {}) => {
    try {
      if (!contract) {
        throw new Error('Contract not initialized');
      }
      
      const tx = await contract[method](...args, options);
      return await tx.wait();
    } catch (error) {
      console.error(`Error calling ${method}:`, error);
      setError(`Error calling ${method}`);
      return null;
    }
  };

  const value = {
    account,
    provider,
    signer,
    contract,
    networkId,
    isConnected,
    error,
    connectWallet,
    disconnectWallet,
    readContract,
    writeContract,
  };

  return (
    <Web3Context.Provider value={value}>
      {children}
    </Web3Context.Provider>
  );
}

// Hook to use Web3 context
export function useWeb3() {
  return useContext(Web3Context);
}
