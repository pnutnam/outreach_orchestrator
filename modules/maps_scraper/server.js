const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const createCsvWriter = require('csv-writer').createObjectCsvWriter;

const PORT = 3000;

const server = http.createServer(async (req, res) => {
    // Serve the HTML file
    if (req.method === 'GET' && req.url === '/') {
        const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(html);
        return;
    }

    // Handle scrape requests
    if (req.method === 'POST' && req.url === '/scrape') {
        let body = '';
        req.on('data', chunk => {
            body += chunk.toString();
        });

        req.on('end', async () => {
            try {
                const { query } = JSON.parse(body);
                console.log(`Starting scrape for: ${query}`);

                // Run the scraper
                const results = await runScraper(query);

                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({
                    success: true,
                    count: results.length,
                    message: 'Scraping completed successfully'
                }));
            } catch (error) {
                console.error('Scraping error:', error);
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({
                    success: false,
                    error: error.message
                }));
            }
        });
        return;
    }

    // 404 for other routes
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('Not Found');
});

async function runScraper(searchQuery) {
    const MAX_RESULTS = 10;
    const browser = await chromium.launch({ headless: false });
    const context = await browser.newContext();
    const page = await context.newPage();

    try {
        console.log(`Searching for: ${searchQuery}`);
        await page.goto('https://www.google.com/maps');

        // Handle cookie consent if it appears
        try {
            await page.click('button[aria-label="Accept all"]', { timeout: 3000 });
        } catch (e) {
            // Ignore if not found
        }

        await page.fill('#searchboxinput', searchQuery);
        await page.keyboard.press('Enter');

        // Wait for results to load
        await page.waitForSelector('div[role="feed"]', { timeout: 10000 });

        // Scroll to load results
        console.log('Scrolling to load results...');
        const feedSelector = 'div[role="feed"]';
        while (true) {
            const results = await page.$$('div[role="article"]');
            if (results.length >= MAX_RESULTS) break;

            await page.evaluate((selector) => {
                const feed = document.querySelector(selector);
                if (feed) feed.scrollTo(0, feed.scrollHeight);
            }, feedSelector);

            await page.waitForTimeout(2000);

            if (results.length > 0 && results.length < MAX_RESULTS) continue;
            break;
        }

        // Collect URLs
        const urls = [];
        const articles = await page.$$('div[role="article"] a[href*="/maps/place/"]');
        for (const article of articles) {
            const href = await article.getAttribute('href');
            if (href && !urls.includes(href)) {
                urls.push(href);
            }
            if (urls.length >= MAX_RESULTS) break;
        }

        console.log(`Collected ${urls.length} URLs to scrape.`);

        const resultsData = [];

        for (const url of urls) {
            console.log(`Scraping: ${url}`);
            try {
                await page.goto(url, { waitUntil: 'domcontentloaded' });

                const data = {
                    url: url,
                    name: '',
                    address: '',
                    phone: '',
                    website: '',
                    rating: '',
                    reviewCount: '',
                    reviews: [],
                    reviewCategories: [],
                    mentionedNames: [],
                    email: ''
                };

                // Extract Basic Details
                try {
                    data.name = await page.textContent('h1');
                } catch (e) { }

                const buttons = await page.$$('button[data-item-id]');
                for (const btn of buttons) {
                    const text = await btn.textContent();
                    const ariaLabel = await btn.getAttribute('aria-label');
                    const itemId = await btn.getAttribute('data-item-id');

                    if (itemId.includes('address')) data.address = ariaLabel || text;
                    if (itemId.includes('phone')) data.phone = ariaLabel || text;
                    if (itemId.includes('authority')) data.website = text;
                }

                const websiteLink = await page.$('a[data-item-id="authority"]');
                if (websiteLink) {
                    data.website = await websiteLink.getAttribute('href');
                }

                // Rating and Review Count
                try {
                    const ratingEl = await page.locator('div[role="img"][aria-label*="stars"]').first();
                    if (await ratingEl.count() > 0) {
                        const aria = await ratingEl.getAttribute('aria-label');
                        data.rating = aria.split(' ')[0];
                    } else {
                        const textRating = await page.locator('span[aria-hidden="true"]').filter({ hasText: /^[0-9]\.[0-9]$/ }).first();
                        if (await textRating.count() > 0) {
                            data.rating = await textRating.textContent();
                        }
                    }

                    const reviewCountEl = await page.getByText(/\([0-9,]+\)/).first();
                    if (await reviewCountEl.count() > 0) {
                        const text = await reviewCountEl.textContent();
                        data.reviewCount = text.replace(/[^0-9]/g, '');
                    } else {
                        const reviewCountText = await page.getByText(/^[0-9,]+ reviews$/).first();
                        if (await reviewCountText.count() > 0) {
                            const text = await reviewCountText.textContent();
                            data.reviewCount = text.replace(/[^0-9]/g, '');
                        }
                    }
                } catch (e) { console.log('Error extracting rating/count:', e.message); }

                // Extract Reviews
                try {
                    const reviewsTabBtn = page.getByRole('tab', { name: /Reviews|Opinions/i });
                    if (await reviewsTabBtn.count() > 0) {
                        await reviewsTabBtn.click();
                        await page.waitForSelector('div[data-review-id]', { timeout: 5000 });

                        const reviewsContainer = await page.locator('div[role="main"] div[tabindex="-1"]').last();
                        if (await reviewsContainer.count() > 0) {
                            for (let i = 0; i < 3; i++) {
                                await reviewsContainer.evaluate(node => node.scrollTo(0, node.scrollHeight));
                                await page.waitForTimeout(1000);
                            }
                        }

                        const moreButtons = await page.$$('button[aria-label*="See more"]');
                        for (const btn of moreButtons.slice(0, 10)) {
                            try {
                                await btn.click();
                                await page.waitForTimeout(200);
                            } catch (e) { }
                        }

                        const reviewElements = await page.$$('div[data-review-id]');
                        for (const reviewEl of reviewElements) {
                            const review = {};
                            try {
                                const reviewerEl = await reviewEl.$('div[class*="d4r55"]') ||
                                    await reviewEl.$('button[data-href*="/contrib/"]') ||
                                    await reviewEl.$('a[href*="/contrib/"]');
                                if (reviewerEl) {
                                    review.reviewer = await reviewerEl.getAttribute('aria-label') || await reviewerEl.textContent();
                                }

                                const starsEl = await reviewEl.$('span[role="img"][aria-label*="stars"]');
                                if (starsEl) {
                                    review.rating = await starsEl.getAttribute('aria-label');
                                }

                                const textEl = await reviewEl.$('span[class*="wiI7pd"]');
                                if (textEl) {
                                    review.text = await textEl.textContent();
                                } else {
                                    const textDiv = await reviewEl.$('div[class*="MyEned"]');
                                    if (textDiv) review.text = await textDiv.textContent();
                                }

                                const timeEl = await reviewEl.$('span[class*="rsqaWe"]');
                                if (timeEl) review.time = await timeEl.textContent();

                            } catch (e) { console.log('Error extracting review details:', e.message); }

                            if (review.reviewer || review.text || review.rating) {
                                data.reviews.push(review);
                            }
                            if (data.reviews.length >= 10) break;
                        }
                    }

                    data.reviewCategories = [];
                    await page.waitForTimeout(1000);

                    const categoryButtons = await page.$$('button.e2moi');
                    for (const btn of categoryButtons) {
                        const ariaLabel = await btn.getAttribute('aria-label');
                        const text = await btn.textContent();
                        const categoryText = ariaLabel || text;

                        if (categoryText && categoryText.includes('mentioned in')) {
                            const match = categoryText.match(/^(.+?),\s*mentioned in (\d+) reviews?$/);
                            if (match) {
                                const subject = match[1];
                                const count = match[2];
                                data.reviewCategories.push(`${subject} (${count})`);
                            } else {
                                data.reviewCategories.push(categoryText.trim());
                            }
                        }
                    }

                    data.mentionedNames = [];
                    const namePattern = /\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b/g;
                    const excludeWords = new Set([
                        'North Beach', 'San Francisco', 'New York', 'Los Angeles', 'Fort Worth', 'Dallas',
                        'South Bay', 'East Bay', 'West Coast', 'East Coast',
                        'Google Maps', 'Yelp Reviews', 'Facebook Page', 'Instagram Account',
                        'The Godfather', 'The Beatles', 'The Rolling',
                        'Monday Morning', 'Tuesday Night', 'Wednesday Evening',
                        'Thank You', 'Best Regards', 'Kind Regards', 'Very Good', 'Highly Recommend',
                        'Perfect Balance', 'Tax Services', 'The Black', 'Bookkeeping Services',
                        'Tax Service', 'Bookkeeping Service', 'Accounting Services', 'Accounting Service',
                        'Financial Services', 'Financial Service', 'Business Services', 'Business Service',
                        'Tax Preparation', 'Tax Consultant', 'Tax Consultants', 'Tax Return',
                        'Income Tax', 'Tax Season', 'Tax Returns', 'Tax Deductions',
                        'Balance Sheet', 'Profit Loss', 'Cash Flow', 'General Ledger'
                    ]);

                    for (const review of data.reviews) {
                        if (review.text) {
                            const matches = review.text.match(namePattern);
                            if (matches) {
                                for (const name of matches) {
                                    const trimmedName = name.trim();
                                    if (!excludeWords.has(trimmedName) &&
                                        !trimmedName.includes('\n') &&
                                        !data.mentionedNames.includes(trimmedName)) {
                                        data.mentionedNames.push(trimmedName);
                                    }
                                }
                            }
                        }
                    }

                } catch (e) {
                    console.log('Error extracting reviews:', e.message);
                }

                // Extract Email
                if (data.website) {
                    try {
                        const page2 = await context.newPage();
                        await page2.goto(data.website, { timeout: 15000, waitUntil: 'domcontentloaded' });
                        const content = await page2.content();
                        const emailRegex = /[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+/gi;
                        const emails = content.match(emailRegex);
                        if (emails) {
                            const uniqueEmails = [...new Set(emails)].filter(email => {
                                const lower = email.toLowerCase();
                                return !lower.match(/\.(png|jpg|jpeg|gif|css|js)$/) &&
                                    !lower.includes('sentry') &&
                                    !lower.includes('wix') &&
                                    !lower.includes('node_modules') &&
                                    !lower.includes('example.com') &&
                                    !lower.includes('domain.com');
                            });
                            data.email = uniqueEmails.join(', ');
                        }
                        await page2.close();
                    } catch (e) {
                        console.log(`Error visiting website ${data.website}: ${e.message}`);
                    }
                }

                resultsData.push(data);

            } catch (e) {
                console.error(`Error processing ${url}:`, e);
            }
        }

        // Export
        const csvWriter = createCsvWriter({
            path: 'results.csv',
            header: [
                { id: 'name', title: 'Name' },
                { id: 'address', title: 'Address' },
                { id: 'phone', title: 'Phone' },
                { id: 'website', title: 'Website' },
                { id: 'rating', title: 'Rating' },
                { id: 'reviewCount', title: 'Review Count' },
                { id: 'reviewCategories', title: 'Mentioned in # of Reviews' },
                { id: 'mentionedNames', title: 'Mentioned Names' },
                { id: 'email', title: 'Email' },
                { id: 'url', title: 'URL' }
            ]
        });

        await csvWriter.writeRecords(resultsData);
        fs.writeFileSync('results.json', JSON.stringify(resultsData, null, 2));

        console.log('Done!');
        await browser.close();

        return resultsData;

    } catch (error) {
        console.error('Fatal error:', error);
        await browser.close();
        throw error;
    }
}

server.listen(PORT, () => {
    console.log(`\n🚀 Server running at http://localhost:${PORT}`);
    console.log(`📊 Open your browser and navigate to the URL above\n`);
});
