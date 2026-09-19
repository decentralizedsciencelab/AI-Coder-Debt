import React, { useState, useEffect } from 'react';
import { useWeb3 } from '../contexts/Web3Context';

function Home() {
  const { isConnected, account, error, readContract, writeContract } = useWeb3();
  const [contractValue, setContractValue] = useState(null);
  const [loading, setLoading] = useState(false);
  
  // Example function to read from contract
  const fetchContractValue = async () => {
    setLoading(true);
    try {
      // Replace 'getValue' with actual contract method
      const value = await readContract('getValue');
      setContractValue(value);
    } catch (error) {
      console.error('Error fetching value:', error);
    } finally {
      setLoading(false);
    }
  };
  
  // Example function to write to contract
  const updateContractValue = async (newValue) => {
    setLoading(true);
    try {
      // Replace 'setValue' with actual contract method
      await writeContract('setValue', [newValue]);
      // Refresh the value
      fetchContractValue();
    } catch (error) {
      console.error('Error updating value:', error);
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    if (isConnected) {
      fetchContractValue();
    }
  }, [isConnected]);

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-8 text-center">Welcome to Our DApp</h1>
      
      {error && (
        <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 mb-8" role="alert">
          <p>{error}</p>
        </div>
      )}
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="bg-white p-6 rounded-lg shadow-md">
          <h2 className="text-xl font-semibold mb-4">Connection Status</h2>
          {isConnected ? (
            <div>
              <p className="text-green-600 font-medium">Connected</p>
              <p className="text-gray-600 mt-2">Account: {account}</p>
            </div>
          ) : (
            <p className="text-yellow-600">Wallet not connected. Please connect your wallet to use the DApp.</p>
          )}
        </div>
        
        <div className="bg-white p-6 rounded-lg shadow-md">
          <h2 className="text-xl font-semibold mb-4">Contract Interaction</h2>
          {isConnected ? (
            <div>
              <p className="mb-4">
                Current Value: {loading ? 'Loading...' : contractValue !== null ? contractValue.toString() : 'N/A'}
              </p>
              
              <div className="mt-4">
                <button 
                  onClick={() => updateContractValue(42)}
                  disabled={loading}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md disabled:opacity-50"
                >
                  {loading ? 'Processing...' : 'Update Value'}
                </button>
              </div>
            </div>
          ) : (
            <p className="text-gray-600">Connect your wallet to interact with the contract.</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default Home;
