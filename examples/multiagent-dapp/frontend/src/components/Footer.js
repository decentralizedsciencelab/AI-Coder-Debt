import React from 'react';

function Footer() {
  return (
    <footer className="bg-gray-800 text-white py-6">
      <div className="container mx-auto px-4">
        <div className="flex flex-col md:flex-row justify-between items-center">
          <div className="mb-4 md:mb-0">
            <h3 className="text-xl font-bold">DApp</h3>
            <p className="text-gray-400 mt-2">Powered by Blockchain Technology</p>
          </div>
          
          <div className="flex space-x-4">
            <a href="https://github.com" target="_blank" rel="noopener noreferrer" className="hover:text-blue-400">
              GitHub
            </a>
            <a href="https://twitter.com" target="_blank" rel="noopener noreferrer" className="hover:text-blue-400">
              Twitter
            </a>
            <a href="https://discord.com" target="_blank" rel="noopener noreferrer" className="hover:text-blue-400">
              Discord
            </a>
          </div>
        </div>
        
        <div className="mt-6 text-center text-gray-400">
          <p>&copy; {new Date().getFullYear()} DApp. All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
}

export default Footer;
