const { chromium } = require('playwright');
const createCsvWriter = require('csv-writer').createObjectCsvWriter;
const fs = require('fs');

const SEARCH_QUERY = process.argv[2] || 'coffee shops in San Francisco';
const MAX_RESULTS = 10;

(async () => {
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();

    try {
        console.log(`Searching for: ${SEARCH_QUERY}`);
        await page.goto('https://www.google.com/maps');

        // Handle cookie consent if it appears (basic handling)
        try {
            await page.click('button[aria-label="Accept all"]', { timeout: 3000 });
        } catch (e) {
            // Ignore if not found
        }

        await page.fill('#searchboxinput', SEARCH_QUERY);
        await page.keyboard.press('Enter');

        // Wait for results to load
        await page.waitForSelector('div[role="feed"]', { timeout: 10000 });

        // Scroll to load at least MAX_RESULTS
        console.log('Scrolling to load results...');
        const feedSelector = 'div[role="feed"]';
        let previousHeight = 0;
        while (true) {
            const results = await page.$$('div[role="article"]'); // Or simpler selector for list items
            if (results.length >= MAX_RESULTS) break;

            await page.evaluate((selector) => {
                const feed = document.querySelector(selector);
                if (feed) feed.scrollTo(0, feed.scrollHeight);
            }, feedSelector);

            await page.waitForTimeout(2000);

            // Break if no new results loaded
            // const currentHeight = await page.evaluate((selector) => document.querySelector(selector).scrollHeight, feedSelector);
            // if (currentHeight === previousHeight) break;
            // previousHeight = currentHeight;

            // Safety break for now
            if (results.length > 0 && results.length < MAX_RESULTS) continue; // Keep scrolling
            break;
        }

        // Get list of result links/elements
        // Note: Google Maps structure is complex. We often click the result in the sidebar.
        // A reliable way is to get the `href` if available or click the element.
        // The list items usually have `a` tags with `href` containing `/maps/place/`.

        const listings = await page.$$('a[href*="/maps/place/"]');
        console.log(`Found ${listings.length} potential listings. Processing first ${MAX_RESULTS}...`);

        const resultsData = [];

        for (let i = 0; i < Math.min(listings.length, MAX_RESULTS); i++) {
            const listing = listings[i];

            // We need to click to open details. 
            // However, if we click, the list might change or we might navigate away.
            // Better strategy: Extract the URL, and visit it? 
            // Or click, scrape, and go back? Going back is risky with dynamic feeds.
            // Let's try clicking and using the same page, assuming the list stays or we can re-query.
            // Actually, `listings` elements might become stale if we navigate.
            // Let's collect URLs first.

            const url = await listing.getAttribute('href');
            if (!url) continue;
        }

        // Re-evaluating strategy: The feed list items are `div[role="article"]`. 
        // Clicking one opens the details in the sidebar (replacing the list usually, or pushing it).
        // Actually, in modern G-Maps, clicking a result often keeps the list on the left or replaces it with details.
        // If it replaces, we need to go back.

        // Let's try a more robust approach:
        // 1. Scrape URLs from the feed.
        // 2. Visit each URL directly.

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

                // Address, Phone, Website usually in buttons or specific divs with icons
                // We can look for aria-labels or specific start-with text

                const buttons = await page.$$('button[data-item-id]');
                for (const btn of buttons) {
                    const text = await btn.textContent();
                    const ariaLabel = await btn.getAttribute('aria-label');
                    const itemId = await btn.getAttribute('data-item-id');

                    if (itemId.includes('address')) data.address = ariaLabel || text;
                    if (itemId.includes('phone')) data.phone = ariaLabel || text;
                    if (itemId.includes('authority')) data.website = text; // Website often has 'authority' in id or is a link
                }

                // Better website selector: `a[data-item-id="authority"]`
                const websiteLink = await page.$('a[data-item-id="authority"]');
                if (websiteLink) {
                    data.website = await websiteLink.getAttribute('href');
                }

                // Rating and Review Count
                try {
                    // Rating is usually in a span with aria-label "4.5 stars" or similar, or just text "4.5"
                    // Review count is usually inside a button or span with text "(1,234)"

                    const ratingEl = await page.locator('div[role="img"][aria-label*="stars"]').first();
                    if (await ratingEl.count() > 0) {
                        const aria = await ratingEl.getAttribute('aria-label');
                        data.rating = aria.split(' ')[0];
                    } else {
                        // Fallback: look for text content "4.x"
                        const textRating = await page.locator('span[aria-hidden="true"]').filter({ hasText: /^[0-9]\.[0-9]$/ }).first();
                        if (await textRating.count() > 0) {
                            data.rating = await textRating.textContent();
                        }
                    }

                    // Review count: look for text starting with "(" and ending with ")" containing numbers
                    const reviewCountEl = await page.getByText(/\([0-9,]+\)/).first();
                    if (await reviewCountEl.count() > 0) {
                        const text = await reviewCountEl.textContent();
                        data.reviewCount = text.replace(/[^0-9]/g, '');
                    } else {
                        // Fallback: look for "1,234 reviews"
                        const reviewCountText = await page.getByText(/^[0-9,]+ reviews$/).first();
                        if (await reviewCountText.count() > 0) {
                            const text = await reviewCountText.textContent();
                            data.reviewCount = text.replace(/[^0-9]/g, '');
                        }
                    }
                } catch (e) { console.log('Error extracting rating/count:', e.message); }

                // Extract Attributes (About Tab)
                try {
                    const aboutTabBtn = page.getByRole('tab', { name: /About/i });
                    if (await aboutTabBtn.count() > 0) {
                        await aboutTabBtn.click();
                        await page.waitForTimeout(1000); // Wait for tab switch

                        // Look for attributes section
                        // Often represented by images/icons with aria-labels or text
                        const attributes = [];

                        // Check for common attribute text
                        const pageContent = await page.content();
                        if (pageContent.includes("Identified as women-owned")) attributes.push("Women-owned");
                        if (pageContent.includes("Identified as veteran-owned")) attributes.push("Veteran-owned");
                        if (pageContent.includes("Identified as Black-owned")) attributes.push("Black-owned");
                        if (pageContent.includes("Identified as Latino-owned")) attributes.push("Latino-owned");

                        data.attributes = attributes;

                        // Go back to Overview or Reviews? Reviews click will handle it.
                    }
                } catch (e) {
                    console.log('Error extracting attributes:', e.message);
                }

                // Extract Reviews

                try {
                    // Click "Reviews" tab using text matching which is more robust
                    const reviewsTabBtn = page.getByRole('tab', { name: /Reviews|Opinions/i });
                    if (await reviewsTabBtn.count() > 0) {
                        await reviewsTabBtn.click();

                        // Wait for reviews to load. They are usually in a scrollable container.
                        // We can wait for a review element to appear.
                        await page.waitForSelector('div[data-review-id]', { timeout: 5000 });

                        // Scroll down to load more reviews and click all "more" buttons
                        const reviewsContainer = await page.locator('div[role="main"] div[tabindex="-1"]').last();
                        if (await reviewsContainer.count() > 0) {
                            // Scroll multiple times to load at least 10 reviews
                            for (let i = 0; i < 3; i++) {
                                await reviewsContainer.evaluate(node => node.scrollTo(0, node.scrollHeight));
                                await page.waitForTimeout(1000);
                            }
                        }

                        // Click all "See more" buttons to expand review text
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

                                // Reviewer Name
                                // Try multiple selectors
                                const reviewerEl = await reviewEl.$('div[class*="d4r55"]') ||
                                    await reviewEl.$('button[data-href*="/contrib/"]') ||
                                    await reviewEl.$('a[href*="/contrib/"]');
                                if (reviewerEl) {
                                    review.reviewer = await reviewerEl.getAttribute('aria-label') || await reviewerEl.textContent();
                                }

                                // Rating
                                const starsEl = await reviewEl.$('span[role="img"][aria-label*="stars"]');
                                if (starsEl) {
                                    review.rating = await starsEl.getAttribute('aria-label');
                                }

                                // Text
                                // wiI7pd is common, but also try generic span with text if that fails? No, too risky.
                                // Let's stick to wiI7pd but also look for the main text container.
                                const textEl = await reviewEl.$('span[class*="wiI7pd"]');
                                if (textEl) {
                                    review.text = await textEl.textContent();
                                } else {
                                    // Fallback: try to find the text block
                                    const textDiv = await reviewEl.$('div[class*="MyEned"]');
                                    if (textDiv) review.text = await textDiv.textContent();
                                }

                                // Time
                                const timeEl = await reviewEl.$('span[class*="rsqaWe"]');
                                if (timeEl) review.time = await timeEl.textContent();

                            } catch (e) { console.log('Error extracting review details:', e.message); }

                            // Only push if we have at least some data
                            if (review.reviewer || review.text || review.rating) {
                                data.reviews.push(review);
                            }
                            if (data.reviews.length >= 10) break;
                        }
                    }

                    // Extract Review Categories (Chips)
                    // These are buttons with class "e2moi" and aria-label containing the category
                    // They appear at the top of the reviews section after clicking the Reviews tab
                    data.reviewCategories = [];

                    // Wait a bit for categories to load
                    await page.waitForTimeout(1000);

                    // Look for buttons with class e2moi (the category chips)
                    const categoryButtons = await page.$$('button.e2moi');
                    for (const btn of categoryButtons) {
                        const ariaLabel = await btn.getAttribute('aria-label');
                        const text = await btn.textContent();

                        // Use aria-label if available, otherwise use text content
                        const categoryText = ariaLabel || text;

                        // Only include if it contains "mentioned in" (actual review categories)
                        // This filters out navigation buttons like "Nearby restaurants", "Hotels", etc.
                        if (categoryText && categoryText.includes('mentioned in')) {
                            // Reformat from "subject, mentioned in X reviews" to "subject (X)"
                            const match = categoryText.match(/^(.+?),\s*mentioned in (\d+) reviews?$/);
                            if (match) {
                                const subject = match[1];
                                const count = match[2];
                                data.reviewCategories.push(`${subject} (${count})`);
                            } else {
                                // Fallback: keep original if pattern doesn't match
                                data.reviewCategories.push(categoryText.trim());
                            }
                        }
                    }


                    // Extract Mentioned Names from review text
                    // Focus on human first+last names only (2 capitalized words, not place names or business names)
                    data.mentionedNames = [];
                    const namePattern = /\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b/g; // First Last (min 3 chars each)
                    const excludeWords = new Set([
                        // Common place/business name patterns
                        'North Beach', 'San Francisco', 'New York', 'Los Angeles', 'Fort Worth', 'Dallas',
                        'South Bay', 'East Bay', 'West Coast', 'East Coast',
                        // Common business/brand patterns
                        'Google Maps', 'Yelp Reviews', 'Facebook Page', 'Instagram Account',
                        // Common title patterns that aren't names
                        'The Godfather', 'The Beatles', 'The Rolling',
                        // Days/Months (already filtered by length but just in case)
                        'Monday Morning', 'Tuesday Night', 'Wednesday Evening',
                        // Common phrases
                        'Thank You', 'Best Regards', 'Kind Regards', 'Very Good', 'Highly Recommend',
                        // Bookkeeping/Business terms
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
                                    // Filter: not in exclude list, no newlines, looks like a human name
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
                            // Filter junk
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
                        // Ensure page is closed even on error
                        if (!page2.isClosed()) await page2.close();
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
    } catch (error) {
        console.error('Fatal error:', error);
        await browser.close();
    }
})();
