const express = require('express');
const router = express.Router();
const contractController = require('../controllers/contractController');

// Get contract information
router.get('/info', contractController.getContractInfo);

// Read contract data
router.get('/read/:method', contractController.readContract);

// Write to contract
router.post('/write/:method', contractController.writeContract);

// Get contract events
router.get('/events/:eventName', contractController.getEvents);

module.exports = router;
