const { ethers } = require('ethers');
const { getProvider } = require('../utils/blockchain');
const logger = require('../utils/logger');

/**
 * Get network status
 */
exports.getNetworkStatus = async (req, res, next) => {
  try {
    const provider = await getProvider();
    const network = await provider.getNetwork();
    
    const networkStatus = {
      chainId: network.chainId,
      name: network.name,
      blockNumber: await provider.getBlockNumber(),
    };
    
    res.status(200).json({ success: true, data: networkStatus });
  } catch (error) {
    logger.error(`Error getting network status: ${error.message}`);
    next(error);
  }
};

/**
 * Get current gas price
 */
exports.getGasPrice = async (req, res, next) => {
  try {
    const provider = await getProvider();
    const feeData = await provider.getFeeData();
    
    const gasData = {
      gasPrice: feeData.gasPrice.toString(),
      maxFeePerGas: feeData.maxFeePerGas ? feeData.maxFeePerGas.toString() : null,
      maxPriorityFeePerGas: feeData.maxPriorityFeePerGas ? feeData.maxPriorityFeePerGas.toString() : null,
    };
    
    res.status(200).json({ success: true, data: gasData });
  } catch (error) {
    logger.error(`Error getting gas price: ${error.message}`);
    next(error);
  }
};

/**
 * Get block information
 */
exports.getBlockInfo = async (req, res, next) => {
  try {
    const { blockNumber } = req.params;
    const provider = await getProvider();
    
    const blockInfo = await provider.getBlock(
      blockNumber === 'latest' ? blockNumber : parseInt(blockNumber, 10)
    );
    
    res.status(200).json({ success: true, data: blockInfo });
  } catch (error) {
    logger.error(`Error getting block info: ${error.message}`);
    next(error);
  }
};
