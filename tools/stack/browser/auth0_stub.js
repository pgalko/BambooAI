// Stand-in for the Auth0 SPA SDK in the local stack: a user is always signed in and the token is a
// fixed string the web app launcher accepts. Never used against a real box.
window.auth0 = {
  createAuth0Client: async function (opts) {
    const user = { sub: 'auth0|localuser', email: 'local@stack', name: 'Local Stack', nickname: 'local' };
    // like the SDK: the session cookie while signed in; `stack.signedout=1` in the cookie jar plays a logged-out browser
    const signedOut = /(^|;\s*)stack\.signedout=1/.test(document.cookie);
    if (!signedOut) document.cookie = 'auth0.local.is.authenticated=true; path=/';
    return {
      isAuthenticated: async () => !signedOut,
      getUser: async () => user,
      getTokenSilently: async () => 'local-token',
      loginWithRedirect: async () => { console.log('[auth0 stub] loginWithRedirect'); },
      handleRedirectCallback: async () => ({}),
      logout: async () => { console.log('[auth0 stub] logout'); window.location.replace(window.location.pathname); }
    };
  }
};
