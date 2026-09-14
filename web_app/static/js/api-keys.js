// api-keys.js - CLEANED VERSION
// This file is now deprecated - all functionality moved to subscription.js
// Keeping only as a stub for any legacy references that might exist

console.log('api-keys.js loaded - functionality now in subscription.js');

// If any other modules still call these functions, redirect to subscription module
if (typeof window !== 'undefined') {
    // Redirect old function calls to subscription module
    window.initializeApiKeysManagement = function() {
        console.log('API keys management now handled by subscription module');
    };
    
    window.checkApiKeysOnLoad = function() {
        console.log('Redirecting to subscription check...');
        if (typeof window.checkSubscriptionOnLoad === 'function') {
            return window.checkSubscriptionOnLoad();
        }
    };
}