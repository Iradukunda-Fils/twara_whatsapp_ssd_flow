# tests/load_test.py

import asyncio
from locust import HttpUser, task, between

class TwaraLoadTest(HttpUser):
    """
    Load testing with Locust.
    
    Usage:
    locust -f tests/load_test.py --host=https://twara.rw
    
    Then open: http://localhost:8089
    """
    
    wait_time = between(1, 3)  # Simulate real user behavior
    
    def on_start(self):
        """Setup test user"""
        self.phone = f"+25078{random.randint(1000000, 9999999)}"
    
    @task(5)  # 50% of requests
    def send_message(self):
        """Simulate incoming WhatsApp message"""
        payload = {
            'entry': [{
                'changes': [{
                    'value': {
                        'messages': [{
                            'from': self.phone,
                            'text': {'body': 'Hey'}
                        }]
                    }
                }]
            }]
        }
        
        with self.client.post(
            "/webhook/whatsapp/",
            json=payload,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status {response.status_code}")
    
    @task(3)  # 30% of requests
    def take_exam(self):
        """Simulate exam flow"""
        # Step 1: Start exam
        self.send_message_text("Ndashaka gukora ikizamini")
        
        # Step 2: Complete exam (simulate)
        time.sleep(18)  # Exam duration
        
        # Step 3: View results
        self.send_message_text("Results")
    
    @task(2)  # 20% of requests
    def subscription_flow(self):
        """Simulate subscription purchase"""
        self.send_message_text("Ndashaka Code")
        time.sleep(1)
        self.send_message_text("Ukwezi")
        time.sleep(1)
        self.send_message_text("0788123456")


# Benchmark script
class PerformanceBenchmark:
    """
    Run performance benchmarks and store results.
    """
    
    @staticmethod
    async def benchmark_state_transitions():
        """
        Measure state transition performance.
        """
        results = {}
        
        for state_name in ['welcome', 'exam', 'exam_result', 'payment_input']:
            session = UserSession('+250788000000')
            session.current_state = state_name
            
            handler = StateRegistry.get_handler(state_name, session)
            
            # Measure on_enter performance
            start = time.time()
            await handler.on_enter()
            duration = time.time() - start
            
            results[state_name] = {
                'on_enter_ms': duration * 1000,
                'memory_usage_mb': self._get_memory_usage()
            }
        
        return results
    
    @staticmethod
    def _get_memory_usage():
        """Get current process memory usage"""
        import psutil
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024  # MB


# Management command
class Command(BaseCommand):
    """
    Run performance benchmarks.
    
    Usage: python manage.py run_benchmarks
    """
    
    def handle(self, *args, **options):
        benchmark = PerformanceBenchmark()
        results = asyncio.run(benchmark.benchmark_state_transitions())
        
        self.stdout.write("\n📊 Performance Benchmark Results:\n")
        
        for state, metrics in results.items():
            self.stdout.write(
                f"  {state}:\n"
                f"    on_enter: {metrics['on_enter_ms']:.2f}ms\n"
                f"    memory: {metrics['memory_usage_mb']:.2f}MB\n"
            )
        
        # Store results for historical tracking
        BenchmarkResult.objects.create(
            timestamp=timezone.now(),
            results=results
        )
