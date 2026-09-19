const { ethers } = require('ethers');
const CONTRACT_ABI = require('../config/contractABI.json');
const logger = require('./logger');

// Contract address
const CONTRACT_ADDRESS = process.env.CONTRACT_ADDRESS;

// Network RPC URL
const RPC_URL = process.env.RPC_URL;

// Private key for signing transactions
const PRIVATE_KEY = process.env.PRIVATE_KEY;

/**
 * Get ethers provider
 */
const getProvider = async () => {
  try {
    return new ethers.JsonRpcProvider(RPC_URL);
  } catch (error) {
    logger.error(`Error getting provider: ${error.message}`);
    throw error;
  }
};

/**
 * Get contract instance
 * @param {boolean} withSigner - Whether to include a signer
 */
const getContract = async (withSigner = false) => {
  try {
    const provider = await getProvider();
    
    if (withSigner && PRIVATE_KEY) {
      const wallet = new ethers.Wallet(PRIVATE_KEY, provider);
      return new ethers.Contract(CONTRACT_ADDRESS, CONTRACT_ABI, wallet);
    }
    
    return new ethers.Contract(CONTRACT_ADDRESS, CONTRACT_ABI, provider);
  } catch (error) {
    logger.error(`Error getting contract: ${error.message}`);
    throw error;
  }
};

module.exports = {
  getProvider,
  getContract
};
