const { ethers } = require('ethers');
const { getProvider, getContract } = require('../utils/blockchain');
const logger = require('../utils/logger');

// Contract ABI and address
const CONTRACT_ABI = require('../config/contractABI.json');
const CONTRACT_ADDRESS = process.env.CONTRACT_ADDRESS;

/**
 * Get contract information
 */
exports.getContractInfo = async (req, res, next) => {
  try {
    const contract = await getContract();
    
    // Get basic contract info
    const contractInfo = {
      address: CONTRACT_ADDRESS,
      network: process.env.NETWORK,
    };
    
    res.status(200).json({ success: true, data: contractInfo });
  } catch (error) {
    logger.error(`Error getting contract info: ${error.message}`);
    next(error);
  }
};

/**
 * Read data from the contract
 */
exports.readContract = async (req, res, next) => {
  try {
    const { method } = req.params;
    const { args = [] } = req.query;
    
    const contract = await getContract();
    
    // Check if the method exists on the contract
    if (typeof contract[method] !== 'function') {
      return res.status(400).json({
        success: false,
        error: `Method ${method} does not exist on the contract`
      });
    }
    
    // Call the contract method
    const result = await contract[method](...JSON.parse(args));
    
    res.status(200).json({ success: true, data: result });
  } catch (error) {
    logger.error(`Error reading from contract: ${error.message}`);
    next(error);
  }
};

/**
 * Write to the contract
 */
exports.writeContract = async (req, res, next) => {
  try {
    const { method } = req.params;
    const { args = [], options = {} } = req.body;
    
    const contract = await getContract(true); // Get contract with signer
    
    // Check if the method exists on the contract
    if (typeof contract[method] !== 'function') {
      return res.status(400).json({
        success: false,
        error: `Method ${method} does not exist on the contract`
      });
    }
    
    // Send the transaction
    const tx = await contract[method](...args, options);
    
    // Wait for transaction to be mined
    const receipt = await tx.wait();
    
    res.status(200).json({
      success: true,
      data: {
        transactionHash: receipt.hash,
        blockNumber: receipt.blockNumber,
        events: receipt.events || []
      }
    });
  } catch (error) {
    logger.error(`Error writing to contract: ${error.message}`);
    next(error);
  }
};

/**
 * Get contract events
 */
exports.getEvents = async (req, res, next) => {
  try {
    const { eventName } = req.params;
    const { fromBlock = 0, toBlock = 'latest', filter = {} } = req.query;
    
    const contract = await getContract();
    
    // Get events
    const events = await contract.queryFilter(
      contract.filters[eventName](...Object.values(filter)),
      fromBlock,
      toBlock
    );
    
    const formattedEvents = events.map(event => ({
      transactionHash: event.transactionHash,
      blockNumber: event.blockNumber,
      args: event.args,
    }));
    
    res.status(200).json({ success: true, data: formattedEvents });
  } catch (error) {
    logger.error(`Error getting events: ${error.message}`);
    next(error);
  }
};
