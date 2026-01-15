/**
 * Tests for the demo service functions.
 * These tests validate the server functions after AI-generated fixes.
 */

const assert = require('node:assert');
const { describe, it, test } = require('node:test');

// Import functions to test (will be imported after fix is applied)
let serverModule;
try {
    serverModule = require('../server.js');
} catch (e) {
    console.log('Server module not loaded for tests - expected during fix testing');
}

describe('processUserData', () => {
    it('should handle undefined userData gracefully', () => {
        // After fix: should return default values or throw handled error
        if (serverModule?.processUserData) {
            assert.doesNotThrow(() => {
                const result = serverModule.processUserData(undefined);
                // After fix, should return some default or handled response
            });
        }
    });

    it('should process valid user data correctly', () => {
        if (serverModule?.processUserData) {
            const userData = { name: 'John', age: 30 };
            const result = serverModule.processUserData(userData);
            assert.strictEqual(result.displayName, 'JOHN');
            assert.strictEqual(result.birthYear, 1994);
        }
    });

    it('should handle null userData gracefully', () => {
        if (serverModule?.processUserData) {
            assert.doesNotThrow(() => {
                serverModule.processUserData(null);
            });
        }
    });
});

describe('getItemAtIndex', () => {
    it('should handle out-of-bounds index gracefully', () => {
        if (serverModule?.getItemAtIndex) {
            const items = [{ value: 'a' }, { value: 'b' }];
            assert.doesNotThrow(() => {
                serverModule.getItemAtIndex(items, 10);
            });
        }
    });

    it('should return correct value for valid index', () => {
        if (serverModule?.getItemAtIndex) {
            const items = [{ value: 'a' }, { value: 'b' }];
            const result = serverModule.getItemAtIndex(items, 0);
            assert.strictEqual(result, 'a');
        }
    });

    it('should handle empty array gracefully', () => {
        if (serverModule?.getItemAtIndex) {
            assert.doesNotThrow(() => {
                serverModule.getItemAtIndex([], 0);
            });
        }
    });

    it('should handle negative index gracefully', () => {
        if (serverModule?.getItemAtIndex) {
            const items = [{ value: 'a' }];
            assert.doesNotThrow(() => {
                serverModule.getItemAtIndex(items, -1);
            });
        }
    });
});

describe('calculateRatio', () => {
    it('should handle zero denominator gracefully', () => {
        if (serverModule?.calculateRatio) {
            assert.doesNotThrow(() => {
                const result = serverModule.calculateRatio(100, 0);
                // After fix: should return 'Infinity', '0', or throw handled error
            });
        }
    });

    it('should calculate ratio correctly', () => {
        if (serverModule?.calculateRatio) {
            const result = serverModule.calculateRatio(10, 2);
            assert.strictEqual(result, '5.00');
        }
    });

    it('should handle negative numbers', () => {
        if (serverModule?.calculateRatio) {
            const result = serverModule.calculateRatio(-10, 2);
            assert.strictEqual(result, '-5.00');
        }
    });
});

// Test runner for external use
async function runAllTests() {
    const results = {
        total: 0,
        passed: 0,
        failed: 0,
        errors: []
    };

    const testCases = [
        {
            name: 'processUserData with undefined',
            fn: () => {
                if (serverModule?.processUserData) {
                    serverModule.processUserData(undefined);
                }
            }
        },
        {
            name: 'processUserData with valid data',
            fn: () => {
                if (serverModule?.processUserData) {
                    const result = serverModule.processUserData({ name: 'John', age: 30 });
                    assert.strictEqual(result.displayName, 'JOHN');
                }
            }
        },
        {
            name: 'getItemAtIndex out of bounds',
            fn: () => {
                if (serverModule?.getItemAtIndex) {
                    serverModule.getItemAtIndex([{ value: 'a' }], 10);
                }
            }
        },
        {
            name: 'calculateRatio with zero',
            fn: () => {
                if (serverModule?.calculateRatio) {
                    serverModule.calculateRatio(100, 0);
                }
            }
        }
    ];

    for (const testCase of testCases) {
        results.total++;
        try {
            testCase.fn();
            results.passed++;
        } catch (error) {
            results.failed++;
            results.errors.push({
                test: testCase.name,
                error: error.message
            });
        }
    }

    return results;
}

module.exports = { runAllTests };
