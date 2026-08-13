import React, { useRef, useState } from 'react';
import { ActivityIndicator, BackHandler, SafeAreaView, StatusBar, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { WebView } from 'react-native-webview';

const PANEL_URL = 'https://scalping-ai-backend-ishr.onrender.com/panel';

export default function App() {
  const webRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [canGoBack, setCanGoBack] = useState(false);

  React.useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (canGoBack && webRef.current) {
        webRef.current.goBack();
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [canGoBack]);

  const reload = () => {
    setError(false);
    setLoading(true);
    webRef.current?.reload();
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#081018" />

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.title}>Scalping AI</Text>
          <Text style={styles.errorText}>Нет соединения с панелью.</Text>
          <TouchableOpacity style={styles.button} onPress={reload}>
            <Text style={styles.buttonText}>Повторить</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <WebView
          ref={webRef}
          source={{ uri: PANEL_URL }}
          style={styles.webview}
          javaScriptEnabled
          domStorageEnabled
          pullToRefreshEnabled
          allowsBackForwardNavigationGestures
          onNavigationStateChange={(nav) => setCanGoBack(nav.canGoBack)}
          onLoadStart={() => setLoading(true)}
          onLoadEnd={() => setLoading(false)}
          onError={() => {
            setLoading(false);
            setError(true);
          }}
          onHttpError={(e) => {
            if (e.nativeEvent.statusCode >= 500) setError(true);
          }}
        />
      )}

      {loading && !error && (
        <View style={styles.loader} pointerEvents="none">
          <ActivityIndicator size="large" color="#20d68f" />
          <Text style={styles.loaderText}>Подключение к Scalping AI…</Text>
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#081018' },
  webview: { flex: 1, backgroundColor: '#081018' },
  loader: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#081018',
  },
  loaderText: { color: '#9eb2c2', marginTop: 14, fontSize: 15 },
  errorBox: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 28 },
  title: { color: '#eef5fb', fontSize: 30, fontWeight: '800', marginBottom: 14 },
  errorText: { color: '#9eb2c2', fontSize: 16, marginBottom: 22 },
  button: { backgroundColor: '#168d62', paddingVertical: 14, paddingHorizontal: 24, borderRadius: 12 },
  buttonText: { color: '#fff', fontWeight: '800', fontSize: 16 },
});
