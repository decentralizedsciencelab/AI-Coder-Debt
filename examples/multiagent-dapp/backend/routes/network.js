const express = require('express');
const router = express.Router();
const networkController = require('../controllers/networkController');

// Get network status
router.get('/status', networkController.getNetworkStatus);

// Get gas price
router.get('/gas-price', networkController.getGasPrice);

// Get block information
router.get('/block/:blockNumber', networkController.getBlockInfo);

module.exports = router;
